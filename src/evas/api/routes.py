"""HTTP routes. Milestone 1: create video (enqueue ingest), list, detail, export."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from evas import storage
from evas.api.schemas import (
    AiRunOut,
    FrameFindingOut,
    JobAccepted,
    ReviewBoardRow,
    VideoCreateRequest,
    VideoDetail,
)
from evas.auth import (
    assert_can_access_client,
    get_current_user,
    require_roles,
    tenancy_client_id,
)
from evas.db import get_session
from evas.enums import JobType, UserRole
from evas.export import build_export, latest_completed_run
from evas.jobs import enqueue
from evas.models import AiFrameFinding, Checklist, Frame, ProcessingJob, Source, User, Video

router = APIRouter()
_staff = require_roles(UserRole.admin, UserRole.reviewer)


@router.post("/videos", response_model=JobAccepted, status_code=202)
def create_video(
    req: VideoCreateRequest,
    session: Session = Depends(get_session),
    user: User = Depends(_staff),
) -> JobAccepted:
    """Register a video for ingestion. Returns the queued ingest job."""
    job = enqueue(
        session,
        job_type=JobType.ingest,
        payload={
            "client_id": str(req.client_id),
            "source_uri": req.source_uri,
            "external_ref": req.external_ref,
            "original_filename": req.original_filename,
            "sampling_override": req.sampling_override,
            "priority": req.priority.value,
        },
    )
    session.flush()
    return JobAccepted(job_id=job.id, job_type=job.job_type.value, status=job.status.value)


@router.get("/videos", response_model=list[ReviewBoardRow])
def list_videos(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    client_id: uuid.UUID | None = None,
    source_id: uuid.UUID | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[ReviewBoardRow]:
    """Video review board (uses the video_review_board view)."""
    # client_viewer is scoped to its own client regardless of the query param.
    scope = tenancy_client_id(user)
    if scope is not None:
        client_id = scope
    # Enrich the (locked) view with duration, frame count, and the checklist
    # name actually used — without modifying the view itself.
    sql = """
        SELECT b.*,
               v.original_filename,
               v.duration_seconds,
               src.label AS source_label,
               (SELECT count(*) FROM frames f WHERE f.video_id = b.id) AS frame_count,
               COALESCE(run_cl.name, active_cl.name) AS checklist_name
        FROM video_review_board b
        JOIN videos v ON v.id = b.id
        LEFT JOIN sources src ON src.id = b.source_id
        LEFT JOIN LATERAL (
            SELECT c.name FROM ai_runs r JOIN checklists c ON c.id = r.checklist_id
            WHERE r.video_id = b.id AND r.status = 'completed'
            ORDER BY r.completed_at DESC LIMIT 1
        ) run_cl ON true
        LEFT JOIN LATERAL (
            SELECT c.name FROM checklists c
            WHERE c.client_id = b.client_id AND c.is_active
            ORDER BY c.version DESC LIMIT 1
        ) active_cl ON true
        WHERE 1=1
    """
    params: dict[str, Any] = {}
    if client_id is not None:
        sql += " AND b.client_id = :client_id"
        params["client_id"] = str(client_id)
    if source_id is not None:
        sql += " AND b.source_id = :source_id"
        params["source_id"] = str(source_id)
    if status is not None:
        sql += " AND b.status = :status"
        params["status"] = status
    sql += " ORDER BY b.uploaded_at DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset
    rows = session.execute(text(sql), params).mappings().all()
    return [ReviewBoardRow(**row) for row in rows]


def _get_active_video(session: Session, video_id: uuid.UUID) -> Video:
    video = session.get(Video, video_id)
    if video is None or video.deleted_at is not None:
        raise HTTPException(status_code=404, detail="video not found")
    return video


@router.get("/videos/{video_id}", response_model=VideoDetail)
def get_video(
    video_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> VideoDetail:
    """Video detail with frames and the latest completed AI run's findings."""
    video = _get_active_video(session, video_id)
    assert_can_access_client(user, video.client_id)
    run = latest_completed_run(session, video_id)

    findings_by_frame: dict[uuid.UUID, AiFrameFinding] = {}
    run_out: AiRunOut | None = None
    if run is not None:
        run_out = AiRunOut(
            id=run.id,
            model=run.model,
            prompt_version=run.prompt_version,
            checklist_id=run.checklist_id,
            status=run.status.value,
            grade=float(run.grade) if run.grade is not None else None,
            summary=run.summary,
            tokens_in=run.tokens_in,
            tokens_out=run.tokens_out,
            cost_usd=float(run.cost_usd),
            completed_at=run.completed_at,
        )
        for f in session.scalars(
            select(AiFrameFinding).where(AiFrameFinding.ai_run_id == run.id)
        ).all():
            findings_by_frame[f.frame_id] = f

    checklist_items: list[dict[str, Any]] | None = None
    if run is not None:
        checklist = session.get(Checklist, run.checklist_id)
        if checklist is not None:
            checklist_items = checklist.items

    frames = session.scalars(
        select(Frame).where(Frame.video_id == video_id).order_by(Frame.frame_index)
    ).all()
    frame_out: list[FrameFindingOut] = []
    for frame in frames:
        finding = findings_by_frame.get(frame.id)
        frame_out.append(
            FrameFindingOut(
                frame_id=frame.id,
                frame_index=frame.frame_index,
                timecode_seconds=float(frame.timecode_seconds),
                timecode_label=frame.timecode_label,
                image_uri=frame.image_uri,
                image_url=None if frame.purged else storage.presign_get(frame.image_uri),
                purged=frame.purged,
                description=finding.description if finding else None,
                findings=finding.findings if finding else None,
                confidence=float(finding.confidence)
                if finding and finding.confidence is not None
                else None,
                flagged=finding.flagged if finding else None,
            )
        )

    return VideoDetail(
        id=video.id,
        client_id=video.client_id,
        external_ref=video.external_ref,
        original_filename=video.original_filename,
        source_uri=video.source_uri,
        status=video.status.value,
        priority=video.priority.value,
        duration_seconds=float(video.duration_seconds)
        if video.duration_seconds is not None
        else None,
        fps=float(video.fps) if video.fps is not None else None,
        width=video.width,
        height=video.height,
        latest_ai_run=run_out,
        checklist_items=checklist_items,
        frames=frame_out,
    )


@router.get("/videos/{video_id}/media")
def get_video_media(
    video_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Presigned URL for the original video so a reviewer can watch/seek it.

    Tenancy-scoped; the URL is short-lived and supports range requests.
    """
    video = _get_active_video(session, video_id)
    assert_can_access_client(user, video.client_id)
    expires_in = 3600
    # Video lives in the source bucket → sign with the source's credentials.
    src = session.get(Source, video.source_id) if video.source_id else None
    cred = src.credential_ref if src else None
    return {
        "url": storage.presign_get(video.source_uri, expires_in=expires_in, credential_ref=cred),
        "expires_in": expires_in,
        "filename": video.original_filename,
        "duration_seconds": float(video.duration_seconds)
        if video.duration_seconds is not None
        else None,
    }


@router.get("/videos/{video_id}/export")
def export_video(
    video_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the findings export document for a video's latest completed run."""
    video = _get_active_video(session, video_id)
    assert_can_access_client(user, video.client_id)
    try:
        return build_export(session, video_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# Job status passthrough (handy for the async ingest flow).
@router.get("/jobs/{job_id}")
def get_job(
    job_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(_staff),
) -> dict[str, Any]:
    job = session.get(ProcessingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "id": str(job.id),
        "job_type": job.job_type.value,
        "status": job.status.value,
        "video_id": str(job.video_id) if job.video_id else None,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "last_error": job.last_error,
    }
