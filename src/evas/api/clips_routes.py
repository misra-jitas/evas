"""Clip (temporal review) endpoints: manual + auto segmentation, clip review."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from evas.api.schemas import ClipCreate, ClipOut, JobAccepted
from evas.audit import write_audit
from evas.auth import require_roles
from evas.clips import auto_segment, create_clip
from evas.db import get_session
from evas.enums import JobType, UserRole
from evas.jobs import enqueue
from evas.models import AiClipFinding, AiRun, Clip, User, Video

router = APIRouter(tags=["clips"])
_staff = require_roles(UserRole.admin, UserRole.reviewer)


def _video_or_404(session: Session, video_id: uuid.UUID) -> Video:
    video = session.get(Video, video_id)
    if video is None or video.deleted_at is not None:
        raise HTTPException(status_code=404, detail="video not found")
    return video


def _to_out(clip: Clip, finding: AiClipFinding | None = None) -> ClipOut:
    return ClipOut(
        id=clip.id,
        video_id=clip.video_id,
        start_seconds=float(clip.start_seconds),
        end_seconds=float(clip.end_seconds),
        label=clip.label,
        description=finding.description if finding else None,
        findings=finding.findings if finding else None,
        confidence=float(finding.confidence)
        if finding and finding.confidence is not None
        else None,
        flagged=finding.flagged if finding else None,
    )


@router.post("/videos/{video_id}/clips", response_model=ClipOut, status_code=201)
def add_clip(
    video_id: uuid.UUID,
    req: ClipCreate,
    session: Session = Depends(get_session),
    user: User = Depends(_staff),
) -> ClipOut:
    _video_or_404(session, video_id)
    try:
        clip = create_clip(session, video_id, req.start_seconds, req.end_seconds, req.label)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    write_audit(
        session,
        entity_type="clip",
        entity_id=clip.id,
        action="created",
        new_value={"start": req.start_seconds, "end": req.end_seconds, "label": req.label},
        user_id=user.id,
    )
    return _to_out(clip)


@router.post("/videos/{video_id}/clips/auto", response_model=list[ClipOut], status_code=201)
def auto_segment_video(
    video_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(_staff),
) -> list[ClipOut]:
    _video_or_404(session, video_id)
    try:
        clips = auto_segment(session, video_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    write_audit(
        session,
        entity_type="video",
        entity_id=video_id,
        action="auto_segmented",
        new_value={"clip_count": len(clips)},
        user_id=user.id,
    )
    return [_to_out(c) for c in clips]


@router.post("/videos/{video_id}/clip-review", response_model=JobAccepted, status_code=202)
def enqueue_clip_review(
    video_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(_staff),
) -> JobAccepted:
    _video_or_404(session, video_id)
    job = enqueue(
        session,
        job_type=JobType.ai_review,
        video_id=video_id,
        payload={"target": "clip"},
    )
    session.flush()
    return JobAccepted(job_id=job.id, job_type=job.job_type.value, status=job.status.value)


@router.get("/videos/{video_id}/clips", response_model=list[ClipOut])
def list_clips(
    video_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(_staff),
) -> list[ClipOut]:
    _video_or_404(session, video_id)
    clips = session.scalars(
        select(Clip).where(Clip.video_id == video_id).order_by(Clip.start_seconds)
    ).all()
    # Attach the most recent finding per clip, if any.
    out: list[ClipOut] = []
    for clip in clips:
        finding = session.scalars(
            select(AiClipFinding)
            .join(AiRun, AiRun.id == AiClipFinding.ai_run_id)
            .where(AiClipFinding.clip_id == clip.id)
            .order_by(AiRun.completed_at.desc())
        ).first()
        out.append(_to_out(clip, finding))
    return out
