"""sync_source step: enumerate a registered source and enqueue ingest per new video.

Payload: {"source_id": "<uuid>"}

Idempotent: a re-scan only enqueues videos whose source_uri is not already
registered for the source's client; ingest itself also dedups by file hash.

The discovered/registered/skipped/failed counts are persisted to
sources.last_sync_result so a partial or failed scan can never look "complete".
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from evas.audit import write_audit
from evas.enums import JobType, SourceStatus, SourceType, VideoPriority
from evas.jobs import enqueue
from evas.models import ProcessingJob, Source, Video
from evas.storage import list_objects

# Object extensions we treat as videos when enumerating a source.
VIDEO_EXTENSIONS = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v")


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _is_video(uri: str) -> bool:
    return uri.lower().endswith(VIDEO_EXTENSIONS)


def handle_sync_source(session: Session, job: ProcessingJob) -> None:
    source_id = uuid.UUID(str(job.payload["source_id"]))
    source = session.get(Source, source_id)
    if source is None or source.deleted_at is not None:
        raise RuntimeError(f"source {source_id} not found")

    if source.type != SourceType.s3:
        # URL enumeration has no defined listing contract yet. Record the error
        # state (committed before we raise, so the source can't sit in 'syncing'),
        # then fail loudly.
        msg = f"source type {source.type.value!r} enumeration is not yet supported"
        source.status = SourceStatus.error
        source.last_error = msg
        source.last_synced_at = _now()
        source.last_sync_result = {
            "discovered": 0,
            "registered": 0,
            "skipped": 0,
            "failed": 0,
            "error": "unsupported_source_type",
            "at": _now().isoformat(),
        }
        write_audit(
            session,
            entity_type="source",
            entity_id=source.id,
            action="sync_failed",
            new_value=source.last_sync_result,
        )
        session.commit()
        raise RuntimeError(msg)

    discovered = registered = linked = skipped = failed = 0
    errors: list[str] = []

    # Existing videos for this client, keyed by source_uri. A video may already
    # exist (ingested via demo, CSV, another source, or a prior sync) — we link
    # it to this source rather than silently skipping, so it shows in the funnel.
    existing_videos = {
        v.source_uri: v
        for v in session.scalars(
            select(Video).where(Video.client_id == source.client_id, Video.deleted_at.is_(None))
        ).all()
    }

    # Enumerate the bucket/prefix. A listing failure (bad bucket, no access,
    # network) must not leave the source stuck in 'syncing' — record the error
    # state, commit, then re-raise so the job retries/dead-letters normally.
    try:
        objects = list_objects(source.uri_prefix, source.credential_ref)
    except Exception as exc:  # noqa: BLE001 - surface any backend/list error as source error
        msg = f"could not list {source.uri_prefix}: {exc!r}"
        source.status = SourceStatus.error
        source.last_error = msg[:500]
        source.last_synced_at = _now()
        source.last_sync_result = {
            "discovered": 0,
            "registered": 0,
            "linked": 0,
            "skipped": 0,
            "failed": 0,
            "error": "list_failed",
            "at": source.last_synced_at.isoformat(),
        }
        write_audit(
            session,
            entity_type="source",
            entity_id=source.id,
            action="sync_failed",
            new_value=source.last_sync_result,
        )
        session.commit()
        raise

    for uri in objects:
        if not _is_video(uri):
            continue
        discovered += 1
        existing = existing_videos.get(uri)
        if existing is not None:
            if existing.source_id is None:
                existing.source_id = source.id
                write_audit(
                    session,
                    entity_type="video",
                    entity_id=existing.id,
                    action="source_linked",
                    new_value={"source_id": str(source.id)},
                )
                linked += 1
            else:
                skipped += 1
            continue
        try:
            enqueue(
                session,
                job_type=JobType.ingest,
                payload={
                    "client_id": str(source.client_id),
                    "source_uri": uri,
                    "source_id": str(source.id),
                    "sampling_override": source.sampling_override,
                    "priority": VideoPriority.normal.value,
                },
            )
            registered += 1
        except Exception as exc:  # noqa: BLE001 - one bad object must not abort the scan
            failed += 1
            errors.append(f"{uri}: {exc!r}")

    source.last_synced_at = _now()
    source.last_sync_result = {
        "discovered": discovered,
        "registered": registered,
        "linked": linked,
        "skipped": skipped,
        "failed": failed,
        "at": source.last_synced_at.isoformat(),
    }
    if failed:
        source.status = SourceStatus.error
        source.last_error = "; ".join(errors[:5])
    else:
        source.status = SourceStatus.connected
        source.last_error = None

    audit_value: dict[str, Any] = dict(source.last_sync_result)
    write_audit(
        session,
        entity_type="source",
        entity_id=source.id,
        action="synced",
        new_value=audit_value,
    )
