"""Client self-serve portal (read-only, tenancy-isolated).

Exposes only client-facing data: no costs, reviewer names, model/prompt info, or
confidence scores. Final findings/grade use the human override where present,
else the AI result.
"""

from __future__ import annotations

import csv
import datetime
import io
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from evas.auth import get_current_user, tenancy_client_id
from evas.db import get_session
from evas.enums import VideoStatus
from evas.export import latest_completed_run
from evas.models import (
    AiFrameFinding,
    Frame,
    HumanFrameNote,
    HumanReview,
    User,
    Video,
)

router = APIRouter(prefix="/portal", tags=["portal"])

_STATUS_LABEL = {
    VideoStatus.ingested: "Processing",
    VideoStatus.frames_extracted: "Processing",
    VideoStatus.ai_reviewed: "In review",
    VideoStatus.human_reviewed: "Reviewed",
    VideoStatus.done: "Reviewed",
    VideoStatus.failed: "Failed",
}


def _scope(user: User, client_id: uuid.UUID | None) -> uuid.UUID:
    """Resolve the client this request is scoped to (enforces tenancy)."""
    own = tenancy_client_id(user)
    if own is not None:
        return own  # client_viewer: always their own client
    if client_id is None:
        raise HTTPException(status_code=400, detail="client_id query param required for staff")
    return client_id


def _final_values(
    ai_findings: dict[str, Any] | None, override: dict[str, Any] | None
) -> dict[str, bool]:
    """Merge AI findings with a human override; return value-only (no confidence)."""
    out: dict[str, bool] = {}
    for key, entry in (ai_findings or {}).items():
        out[key] = bool((entry or {}).get("value"))
    for key, entry in (override or {}).items():
        out[key] = bool((entry or {}).get("value"))
    return out


def _human_review(session: Session, video_id: uuid.UUID) -> HumanReview | None:
    return session.scalars(
        select(HumanReview)
        .where(HumanReview.video_id == video_id, HumanReview.is_qa_review.is_(False))
        .order_by(HumanReview.reviewed_at.desc().nullslast())
    ).first()


@router.get("/videos")
def portal_videos(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    client_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    cid = _scope(user, client_id)
    videos = session.scalars(
        select(Video)
        .where(Video.client_id == cid, Video.deleted_at.is_(None))
        .order_by(Video.uploaded_at.desc())
    ).all()
    out: list[dict[str, Any]] = []
    for v in videos:
        run = latest_completed_run(session, v.id)
        hr = _human_review(session, v.id)
        final_grade = (
            float(hr.grade)
            if hr and hr.grade is not None
            else float(run.grade)
            if run and run.grade is not None
            else None
        )
        out.append(
            {
                "id": str(v.id),
                "external_ref": v.external_ref,
                "uploaded_at": v.uploaded_at.isoformat(),
                "status": _STATUS_LABEL.get(v.status, "Processing"),
                "final_grade": final_grade,
            }
        )
    return out


def _video_or_404(
    session: Session, user: User, video_id: uuid.UUID, client_id: uuid.UUID | None
) -> Video:
    cid = _scope(user, client_id)
    video = session.get(Video, video_id)
    if video is None or video.deleted_at is not None or video.client_id != cid:
        raise HTTPException(status_code=404, detail="not found")
    return video


@router.get("/videos/{video_id}")
def portal_video_detail(
    video_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    client_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    video = _video_or_404(session, user, video_id, client_id)
    run = latest_completed_run(session, video.id)
    hr = _human_review(session, video.id)

    ai_by_frame: dict[uuid.UUID, AiFrameFinding] = {}
    if run is not None:
        for f in session.scalars(
            select(AiFrameFinding).where(AiFrameFinding.ai_run_id == run.id)
        ).all():
            ai_by_frame[f.frame_id] = f
    overrides: dict[uuid.UUID, HumanFrameNote] = {}
    if hr is not None:
        for n in session.scalars(
            select(HumanFrameNote).where(HumanFrameNote.human_review_id == hr.id)
        ).all():
            overrides[n.frame_id] = n

    frames = session.scalars(
        select(Frame).where(Frame.video_id == video.id).order_by(Frame.frame_index)
    ).all()
    notable: list[dict[str, Any]] = []
    for frame in frames:
        ai = ai_by_frame.get(frame.id)
        note = overrides.get(frame.id)
        # Notable = flagged by AI or carrying a human note/override.
        if not ((ai and ai.flagged) or note):
            continue
        notable.append(
            {
                "timecode_label": frame.timecode_label,
                "findings": _final_values(
                    ai.findings if ai else None, note.override_findings if note else None
                ),
                "note": note.note if note else None,
            }
        )

    final_grade = (
        float(hr.grade)
        if hr and hr.grade is not None
        else float(run.grade)
        if run and run.grade is not None
        else None
    )
    return {
        "id": str(video.id),
        "external_ref": video.external_ref,
        "status": _STATUS_LABEL.get(video.status, "Processing"),
        "final_grade": final_grade,
        "summary": run.summary if run else None,
        "notable_frames": notable,
    }


@router.get("/export.csv")
def portal_export_csv(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    client_id: uuid.UUID | None = None,
    date_from: datetime.date | None = Query(None),
    date_to: datetime.date | None = Query(None),
) -> Response:
    cid = _scope(user, client_id)
    stmt = select(Video).where(Video.client_id == cid, Video.deleted_at.is_(None))
    if date_from is not None:
        stmt = stmt.where(
            Video.uploaded_at
            >= datetime.datetime.combine(date_from, datetime.time.min, datetime.UTC)
        )
    if date_to is not None:
        stmt = stmt.where(
            Video.uploaded_at <= datetime.datetime.combine(date_to, datetime.time.max, datetime.UTC)
        )
    videos = session.scalars(stmt.order_by(Video.uploaded_at)).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["external_ref", "uploaded_at", "status", "final_grade"])
    for v in videos:
        run = latest_completed_run(session, v.id)
        hr = _human_review(session, v.id)
        final_grade = (
            float(hr.grade)
            if hr and hr.grade is not None
            else float(run.grade)
            if run and run.grade is not None
            else None
        )
        writer.writerow(
            [
                v.external_ref or "",
                v.uploaded_at.isoformat(),
                _STATUS_LABEL.get(v.status, "Processing"),
                final_grade,
            ]
        )
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=evas_findings.csv"},
    )
