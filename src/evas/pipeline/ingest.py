"""ingest step: register a video (sha256 dedup), ffprobe metadata.

Payload: {client_id, source_uri, external_ref?, original_filename?,
          sampling_override?, priority?}
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from evas.audit import record_status_change, write_audit
from evas.config import get_settings
from evas.enums import JobType, VideoPriority, VideoStatus
from evas.jobs import enqueue
from evas.media import probe_video
from evas.models import ProcessingJob, Video
from evas.storage import download_to_file


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def handle_ingest(session: Session, job: ProcessingJob) -> None:
    payload = job.payload
    client_id = uuid.UUID(str(payload["client_id"]))
    source_uri = str(payload["source_uri"])

    settings = get_settings()
    os.makedirs(settings.work_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=settings.work_dir, suffix=os.path.splitext(source_uri)[1])
    os.close(fd)
    try:
        download_to_file(source_uri, tmp_path)
        file_hash = _sha256_file(tmp_path)

        # Idempotent: dedup on (client_id, file_hash).
        existing = session.scalars(
            select(Video).where(
                Video.client_id == client_id,
                Video.file_hash == file_hash,
                Video.deleted_at.is_(None),
            )
        ).first()
        if existing is not None:
            job.video_id = existing.id
            write_audit(
                session,
                entity_type="video",
                entity_id=existing.id,
                action="ingest_deduped",
                new_value={"source_uri": source_uri, "file_hash": file_hash},
            )
            return

        probe = probe_video(tmp_path)
        source_ref = payload.get("source_id")
        video = Video(
            client_id=client_id,
            source_id=uuid.UUID(str(source_ref)) if source_ref else None,
            external_ref=payload.get("external_ref"),
            original_filename=payload.get("original_filename"),
            source_uri=source_uri,
            file_hash=file_hash,
            size_bytes=probe.size_bytes,
            duration_seconds=Decimal(str(probe.duration_seconds))
            if probe.duration_seconds is not None
            else None,
            fps=Decimal(str(probe.fps)) if probe.fps is not None else None,
            width=probe.width,
            height=probe.height,
            codec=probe.codec,
            metadata_=probe.raw,
            sampling_override=payload.get("sampling_override"),
            status=VideoStatus.ingested,
            priority=VideoPriority(payload.get("priority", "normal")),
        )
        session.add(video)
        session.flush()  # assign video.id

        job.video_id = video.id
        write_audit(
            session,
            entity_type="video",
            entity_id=video.id,
            action="created",
            new_value={"source_uri": source_uri, "file_hash": file_hash},
        )
        record_status_change(
            session,
            entity_type="video",
            entity_id=video.id,
            old_status=None,
            new_status=VideoStatus.ingested.value,
        )
        enqueue(session, job_type=JobType.extract_frames, video_id=video.id)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
