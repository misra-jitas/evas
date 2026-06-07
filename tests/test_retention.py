"""Retention: purge_frames (keep rows), archive, and the retention-sweep CLI."""

from __future__ import annotations

import uuid
from decimal import Decimal

from click.testing import CliRunner
from sqlalchemy import select

from evas import worker
from evas.cli import cli
from evas.db import session_scope
from evas.enums import JobType
from evas.jobs import enqueue
from evas.models import AuditLog, Client, Frame, ProcessingJob, Video


def _seed_video_with_frames(n: int, *, retention_days=None, archive_days=None) -> uuid.UUID:
    with session_scope() as s:
        c = Client(
            name="Acme",
            slug=f"acme-{uuid.uuid4().hex[:6]}",
            sampling_config={},
            frame_retention_days=retention_days,
            video_archive_days=archive_days,
        )
        s.add(c)
        s.flush()
        v = Video(client_id=c.id, source_uri="s3://b/v.mp4", file_hash=uuid.uuid4().hex)
        s.add(v)
        s.flush()
        for i in range(n):
            s.add(
                Frame(
                    video_id=v.id,
                    frame_index=i,
                    timecode_seconds=Decimal(i),
                    timecode_label=f"00:00:0{i}.000",
                    image_uri=f"s3://frames/{v.id}/{i}.jpg",
                )
            )
        return v.id


def test_purge_frames_keeps_rows(fake_s3) -> None:
    video_id = _seed_video_with_frames(3)
    with session_scope() as s:
        frames = s.scalars(select(Frame).where(Frame.video_id == video_id)).all()
        for f in frames:
            fake_s3.put(f.image_uri, b"jpegbytes")
        enqueue(s, job_type=JobType.purge_frames, video_id=video_id)

    assert worker.run_once() is True

    with session_scope() as s:
        frames = s.scalars(select(Frame).where(Frame.video_id == video_id)).all()
        assert len(frames) == 3  # rows kept
        assert all(f.purged for f in frames)
        audit = s.scalars(select(AuditLog).where(AuditLog.action == "frames_purged")).all()
        assert len(audit) == 1
    assert fake_s3.store == {}  # images deleted

    # Idempotent: re-running purges nothing new.
    with session_scope() as s:
        enqueue(s, job_type=JobType.purge_frames, video_id=video_id)
    worker.run_once()
    with session_scope() as s:
        assert len(s.scalars(select(AuditLog).where(AuditLog.action == "frames_purged")).all()) == 1


def test_archive_marks_metadata(fake_s3) -> None:
    video_id = _seed_video_with_frames(1)
    with session_scope() as s:
        enqueue(s, job_type=JobType.archive, video_id=video_id)
    assert worker.run_once() is True

    with session_scope() as s:
        v = s.get(Video, video_id)
        assert v.metadata_.get("archived") is True
        assert "archived_at" in v.metadata_
        assert s.scalars(select(AuditLog).where(AuditLog.action == "archived")).all()


def test_retention_sweep_enqueues_jobs() -> None:
    # retention_days=0 / archive_days=0 -> every video is immediately eligible.
    video_id = _seed_video_with_frames(2, retention_days=0, archive_days=0)

    result = CliRunner().invoke(cli, ["retention-sweep"])
    assert result.exit_code == 0, result.output

    with session_scope() as s:
        jobs = {
            j.job_type
            for j in s.scalars(
                select(ProcessingJob).where(ProcessingJob.video_id == video_id)
            ).all()
        }
        assert JobType.purge_frames in jobs
        assert JobType.archive in jobs
