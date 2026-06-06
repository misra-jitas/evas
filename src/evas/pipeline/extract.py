"""extract_frames step: sample frames per sampling config, upload to S3.

Reads sampling from video.sampling_override, falling back to the client's
sampling_config. Idempotent: if frames already exist for the video it re-uses
them rather than duplicating.
"""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from evas.audit import record_status_change
from evas.config import get_settings
from evas.enums import JobType, VideoStatus
from evas.jobs import enqueue
from evas.media import extract_frames
from evas.models import Client, Frame, ProcessingJob, Video
from evas.storage import download_to_file, upload_file

_DEFAULT_SAMPLING = {"interval_seconds": 5, "max_frames": 300, "frame_width": 1280}


def _resolve_sampling(video: Video, client: Client) -> dict[str, Any]:
    cfg = dict(_DEFAULT_SAMPLING)
    cfg.update(client.sampling_config or {})
    cfg.update(video.sampling_override or {})
    return cfg


def handle_extract_frames(session: Session, job: ProcessingJob) -> None:
    if job.video_id is None:
        raise ValueError("extract_frames job has no video_id")
    video = session.get(Video, job.video_id)
    if video is None:
        raise ValueError(f"video {job.video_id} not found")
    client = session.get(Client, video.client_id)
    if client is None:
        raise ValueError(f"client {video.client_id} not found")

    existing = session.scalar(
        select(func.count()).select_from(Frame).where(Frame.video_id == video.id)
    )
    if existing:
        # Already extracted (likely a retry); ensure downstream is queued.
        _advance(session, video)
        return

    cfg = _resolve_sampling(video, client)
    settings = get_settings()
    os.makedirs(settings.work_dir, exist_ok=True)
    fd, tmp_video = tempfile.mkstemp(
        dir=settings.work_dir, suffix=os.path.splitext(video.source_uri)[1]
    )
    os.close(fd)
    work_dir = tempfile.mkdtemp(dir=settings.work_dir, prefix=f"frames_{video.id}_")
    try:
        download_to_file(video.source_uri, tmp_video)
        frames = extract_frames(
            tmp_video,
            work_dir,
            interval_seconds=float(cfg["interval_seconds"]),
            max_frames=int(cfg["max_frames"]),
            frame_width=int(cfg["frame_width"]),
        )
        for f in frames:
            key = f"clients/{video.client_id}/videos/{video.id}/frame_{f.index:06d}.jpg"
            uri = upload_file(
                f.local_path, settings.s3_bucket_frames, key, content_type="image/jpeg"
            )
            session.add(
                Frame(
                    video_id=video.id,
                    frame_index=f.index,
                    timecode_seconds=Decimal(str(round(f.timecode_seconds, 3))),
                    timecode_label=f.timecode_label,
                    image_uri=uri,
                )
            )
        _advance(session, video)
    finally:
        for path in (tmp_video,):
            if os.path.exists(path):
                os.remove(path)
        for name in os.listdir(work_dir) if os.path.isdir(work_dir) else []:
            os.remove(os.path.join(work_dir, name))
        if os.path.isdir(work_dir):
            os.rmdir(work_dir)


def _advance(session: Session, video: Video) -> None:
    if video.status == VideoStatus.ingested:
        old = video.status.value
        video.status = VideoStatus.frames_extracted
        record_status_change(
            session,
            entity_type="video",
            entity_id=video.id,
            old_status=old,
            new_status=VideoStatus.frames_extracted.value,
        )
    enqueue(session, job_type=JobType.ai_review, video_id=video.id)
