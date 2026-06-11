"""Sources: register a place full of videos, then scan it to enqueue ingest.

Admin-only. A source's funnel (to_ingest / ingested / in_review / done / failed)
is derived from its videos' statuses plus pending ingest jobs.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from evas.api.schemas import JobAccepted, SourceCreate, SourceFunnel, SourceOut, SourceUpdate
from evas.audit import write_audit
from evas.auth import require_roles
from evas.db import get_session
from evas.enums import JobStatus, JobType, SourceStatus, UserRole, VideoStatus
from evas.jobs import enqueue
from evas.models import ProcessingJob, Source, User, Video
from evas.storage import configured_credential_refs

router = APIRouter(prefix="/sources", tags=["sources"])
_admin = require_roles(UserRole.admin)

# video_status -> funnel bucket
_BUCKET = {
    VideoStatus.ingested: "ingested",
    VideoStatus.frames_extracted: "ingested",
    VideoStatus.ai_reviewed: "in_review",
    VideoStatus.human_reviewed: "done",
    VideoStatus.done: "done",
    VideoStatus.failed: "failed",
}


def _funnel(session: Session, source_id: uuid.UUID) -> SourceFunnel:
    counts = {"to_ingest": 0, "ingested": 0, "in_review": 0, "done": 0, "failed": 0}
    rows = session.execute(
        select(Video.status, func.count())
        .where(Video.source_id == source_id, Video.deleted_at.is_(None))
        .group_by(Video.status)
    ).all()
    for status, n in rows:
        counts[_BUCKET[status]] += int(n)
    # Discovered-but-not-yet-ingested: ingest jobs still pending for this source.
    counts["to_ingest"] = int(
        session.scalar(
            select(func.count())
            .select_from(ProcessingJob)
            .where(
                ProcessingJob.job_type == JobType.ingest,
                ProcessingJob.status.in_([JobStatus.queued, JobStatus.running]),
                ProcessingJob.payload["source_id"].astext == str(source_id),
            )
        )
        or 0
    )
    total = sum(counts.values())
    return SourceFunnel(total=total, **counts)


def _to_out(session: Session, source: Source) -> SourceOut:
    return SourceOut(
        id=source.id,
        client_id=source.client_id,
        label=source.label,
        type=source.type.value,
        uri_prefix=source.uri_prefix,
        credential_ref=source.credential_ref,
        sampling_override=source.sampling_override,
        status=source.status.value,
        auto_sync=source.auto_sync,
        last_synced_at=source.last_synced_at,
        last_error=source.last_error,
        last_sync_result=source.last_sync_result,
        created_at=source.created_at,
        funnel=_funnel(session, source.id),
    )


def _get_active(session: Session, source_id: uuid.UUID) -> Source:
    source = session.get(Source, source_id)
    if source is None or source.deleted_at is not None:
        raise HTTPException(status_code=404, detail="source not found")
    return source


@router.post("", response_model=SourceOut, status_code=201)
def create_source(
    req: SourceCreate,
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
) -> SourceOut:
    status = SourceStatus.syncing if req.scan_now else SourceStatus.connected
    # (client_id, uri_prefix) is unique (incl. soft-deleted rows). An active
    # duplicate is a clean 409; a soft-deleted one is revived rather than
    # dead-ending on the constraint (delete-then-readd should just work).
    existing = session.scalar(
        select(Source).where(Source.client_id == req.client_id, Source.uri_prefix == req.uri_prefix)
    )
    if existing is not None and existing.deleted_at is None:
        raise HTTPException(
            status_code=409, detail="a source with this prefix already exists for this client"
        )
    if existing is not None:  # revive a previously soft-deleted source
        existing.deleted_at = None
        existing.label = req.label
        existing.type = req.type
        existing.credential_ref = req.credential_ref
        existing.sampling_override = req.sampling_override
        existing.auto_sync = req.auto_sync
        existing.status = status
        existing.last_error = None
        source = existing
        action = "recreated"
    else:
        source = Source(
            client_id=req.client_id,
            label=req.label,
            type=req.type,
            uri_prefix=req.uri_prefix,
            credential_ref=req.credential_ref,
            sampling_override=req.sampling_override,
            auto_sync=req.auto_sync,
            status=status,
        )
        session.add(source)
        action = "created"
    session.flush()
    write_audit(
        session,
        entity_type="source",
        entity_id=source.id,
        action=action,
        new_value={"label": source.label, "uri_prefix": source.uri_prefix},
        user_id=user.id,
    )
    if req.scan_now:
        enqueue(session, job_type=JobType.sync_source, payload={"source_id": str(source.id)})
    session.flush()
    return _to_out(session, source)


@router.get("", response_model=list[SourceOut])
def list_sources(
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
    client_id: uuid.UUID | None = None,
) -> list[SourceOut]:
    stmt = select(Source).where(Source.deleted_at.is_(None)).order_by(Source.created_at.desc())
    if client_id is not None:
        stmt = stmt.where(Source.client_id == client_id)
    return [_to_out(session, s) for s in session.scalars(stmt).all()]


@router.get("/credentials")
def list_credentials(user: User = Depends(_admin)) -> dict[str, list[str]]:
    """Credential refs that have keys configured in env, for the register form.

    Declared before /{source_id} so "credentials" isn't parsed as an id.
    """
    return {"refs": configured_credential_refs()}


@router.get("/{source_id}", response_model=SourceOut)
def get_source(
    source_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
) -> SourceOut:
    return _to_out(session, _get_active(session, source_id))


@router.patch("/{source_id}", response_model=SourceOut)
def update_source(
    source_id: uuid.UUID,
    req: SourceUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
) -> SourceOut:
    source = _get_active(session, source_id)
    if req.label is not None:
        source.label = req.label
    if req.credential_ref is not None:
        source.credential_ref = req.credential_ref
    if req.sampling_override is not None:
        source.sampling_override = req.sampling_override
    if req.auto_sync is not None:
        source.auto_sync = req.auto_sync
    if req.enabled is not None:
        # Don't clobber a transient 'syncing'/'error' unless explicitly toggling.
        source.status = SourceStatus.connected if req.enabled else SourceStatus.disabled
    write_audit(
        session,
        entity_type="source",
        entity_id=source.id,
        action="updated",
        new_value=req.model_dump(exclude_none=True),
        user_id=user.id,
    )
    session.flush()
    return _to_out(session, source)


@router.delete("/{source_id}", status_code=204)
def delete_source(
    source_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
) -> None:
    import datetime

    source = _get_active(session, source_id)
    source.deleted_at = datetime.datetime.now(datetime.UTC)
    write_audit(
        session,
        entity_type="source",
        entity_id=source.id,
        action="deleted",
        user_id=user.id,
    )


@router.post("/{source_id}/sync", response_model=JobAccepted, status_code=202)
def sync_source(
    source_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
) -> JobAccepted:
    source = _get_active(session, source_id)
    if source.status == SourceStatus.disabled:
        raise HTTPException(status_code=409, detail="source is disabled")
    source.status = SourceStatus.syncing
    job = enqueue(session, job_type=JobType.sync_source, payload={"source_id": str(source.id)})
    session.flush()
    return JobAccepted(job_id=job.id, job_type=job.job_type.value, status=job.status.value)
