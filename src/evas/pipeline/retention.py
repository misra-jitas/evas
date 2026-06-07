"""Retention steps: purge_frames (delete frame images, keep rows) and archive.

Both are idempotent and audited. purge_frames deletes only non-purged frames'
S3 objects and flips frames.purged=true; the frames row is always kept.
"""

from __future__ import annotations

import contextlib
import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from evas.audit import write_audit
from evas.models import Frame, ProcessingJob, Video
from evas.storage import delete_object


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def handle_purge_frames(session: Session, job: ProcessingJob) -> None:
    if job.video_id is None:
        raise ValueError("purge_frames job has no video_id")
    frames = session.scalars(
        select(Frame).where(Frame.video_id == job.video_id, Frame.purged.is_(False))
    ).all()
    purged = 0
    for frame in frames:
        # Image may already be gone; mark purged regardless.
        with contextlib.suppress(Exception):
            delete_object(frame.image_uri)
        frame.purged = True
        purged += 1
    if purged:
        write_audit(
            session,
            entity_type="video",
            entity_id=job.video_id,
            action="frames_purged",
            new_value={"purged_count": purged},
        )


def handle_archive(session: Session, job: ProcessingJob) -> None:
    if job.video_id is None:
        raise ValueError("archive job has no video_id")
    video = session.get(Video, job.video_id)
    if video is None:
        raise ValueError(f"video {job.video_id} not found")
    if video.metadata_.get("archived"):
        return  # idempotent
    video.metadata_ = {
        **video.metadata_,
        "archived": True,
        "archived_at": _utcnow().isoformat(),
    }
    write_audit(
        session,
        entity_type="video",
        entity_id=video.id,
        action="archived",
        new_value={"source_uri": video.source_uri},
    )
