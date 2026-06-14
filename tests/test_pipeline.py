"""End-to-end pipeline test: ingest -> extract_frames -> ai_review.

Uses real ffmpeg/ffprobe, a fake in-memory S3, and a fake AI reviewer.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from evas import worker
from evas.checklists import EXAMPLE_CHECKLIST_ITEMS, EXAMPLE_CHECKLIST_NAME
from evas.db import session_scope
from evas.enums import JobType, RunStatus, VideoStatus
from evas.jobs import enqueue
from evas.models import AiFrameFinding, AiRun, AuditLog, Checklist, Client, Frame, Video


def _seed_client() -> uuid.UUID:
    with session_scope() as s:
        client = Client(
            name="Acme",
            slug=f"acme-{uuid.uuid4().hex[:8]}",
            sampling_config={"interval_seconds": 1, "max_frames": 3, "frame_width": 160},
        )
        s.add(client)
        s.flush()
        s.add(
            Checklist(
                client_id=client.id,
                name=EXAMPLE_CHECKLIST_NAME,
                version=1,
                items=EXAMPLE_CHECKLIST_ITEMS,
                is_active=True,
            )
        )
        return client.id


def _drain() -> int:
    n = 0
    while worker.run_once():
        n += 1
    return n


def test_full_pipeline(fake_s3, fake_ai, sample_video_bytes) -> None:
    client_id = _seed_client()
    source_uri = "s3://evas-videos/acme/sample.mp4"
    fake_s3.put(source_uri, sample_video_bytes)

    with session_scope() as s:
        enqueue(
            s,
            job_type=JobType.ingest,
            payload={"client_id": str(client_id), "source_uri": source_uri},
        )

    processed = _drain()
    assert processed >= 3  # ingest + extract_frames + ai_review

    with session_scope() as s:
        video = s.scalars(select(Video)).one()
        assert video.status == VideoStatus.ai_reviewed
        assert video.file_hash  # sha256 recorded
        assert video.duration_seconds is not None  # ffprobe ran

        frame_count = s.scalar(
            select(func.count()).select_from(Frame).where(Frame.video_id == video.id)
        )
        assert frame_count == 3

        run = s.scalars(select(AiRun).where(AiRun.video_id == video.id)).one()
        assert run.status == RunStatus.completed
        assert run.grade is not None
        assert run.tokens_in > 0

        findings = s.scalars(select(AiFrameFinding).where(AiFrameFinding.ai_run_id == run.id)).all()
        assert len(findings) == frame_count
        # holding_broom is low-confidence in the fake -> every frame flagged.
        assert all(f.flagged for f in findings)

        # Status changes were audited (video None->ingested, ->frames_extracted, ->ai_reviewed).
        status_changes = s.scalars(
            select(AuditLog).where(
                AuditLog.entity_type == "video", AuditLog.action == "status_changed"
            )
        ).all()
        assert len(status_changes) == 3


def test_resample_reextracts_at_new_rate(fake_s3, fake_ai, sample_video_bytes) -> None:
    client_id = _seed_client()  # interval 1s, max_frames 3
    source_uri = "s3://evas-videos/acme/resample.mp4"
    fake_s3.put(source_uri, sample_video_bytes)
    with session_scope() as s:
        enqueue(
            s,
            job_type=JobType.ingest,
            payload={"client_id": str(client_id), "source_uri": source_uri},
        )
    _drain()

    with session_scope() as s:
        video = s.scalars(select(Video)).one()
        vid = video.id
        before = s.scalar(select(func.count()).select_from(Frame).where(Frame.video_id == vid))

        # Re-enqueue extract WITHOUT resample → idempotent no-op (count unchanged).
        enqueue(s, job_type=JobType.extract_frames, video_id=vid)
    _drain()
    with session_scope() as s:
        same = s.scalar(select(func.count()).select_from(Frame).where(Frame.video_id == vid))
        assert same == before

        # Change the rate and force a resample.
        video = s.get(Video, vid)
        assert video is not None
        video.sampling_override = {"interval_seconds": 0.5, "max_frames": 6, "frame_width": 160}
        enqueue(s, job_type=JobType.extract_frames, video_id=vid, payload={"resample": True})
    _drain()

    with session_scope() as s:
        after = s.scalar(select(func.count()).select_from(Frame).where(Frame.video_id == vid))
        assert after > before  # denser sample at 0.5s vs 1s
        # A fresh ai_review ran on the new frames; old findings were cascade-deleted.
        runs = s.scalars(select(AiRun).where(AiRun.video_id == vid)).all()
        assert len(runs) >= 2
        latest = max(runs, key=lambda r: r.created_at)
        findings = s.scalars(
            select(AiFrameFinding).where(AiFrameFinding.ai_run_id == latest.id)
        ).all()
        assert len(findings) == after


def test_ingest_dedup(fake_s3, sample_video_bytes) -> None:
    client_id = _seed_client()
    source_uri = "s3://evas-videos/acme/dup.mp4"
    fake_s3.put(source_uri, sample_video_bytes)

    for _ in range(2):
        with session_scope() as s:
            enqueue(
                s,
                job_type=JobType.ingest,
                payload={"client_id": str(client_id), "source_uri": source_uri},
            )
        # Process just the ingest job we queued.
        worker.run_once()

    with session_scope() as s:
        assert s.scalar(select(func.count()).select_from(Video)) == 1


def test_failure_dead_letters() -> None:
    # ai_review with no checklist for the client -> handler raises every attempt.
    with session_scope() as s:
        client = Client(name="NoChecklist", slug=f"nc-{uuid.uuid4().hex[:8]}", sampling_config={})
        s.add(client)
        s.flush()
        video = Video(
            client_id=client.id,
            source_uri="s3://x/y.mp4",
            file_hash=uuid.uuid4().hex,
            status=VideoStatus.frames_extracted,
        )
        s.add(video)
        s.flush()
        enqueue(s, job_type=JobType.ai_review, video_id=video.id, max_attempts=2)

    # First attempt -> requeued, second -> dead.
    assert worker.run_once() is True
    assert worker.run_once() is True
    assert worker.run_once() is False  # nothing left to claim

    from evas.enums import JobStatus
    from evas.models import ProcessingJob

    with session_scope() as s:
        job = s.scalars(select(ProcessingJob)).one()
        assert job.status == JobStatus.dead
        assert job.attempts == 2
        assert job.last_error
