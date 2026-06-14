"""AI Review observability (admin): what the agent actually reviewed, found, and cost.

Read-only over ai_runs / ai_frame_findings / processing_jobs (no schema change),
plus a Re-run action that creates a *new* run (never overwrites history).
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from evas import storage
from evas.api.schemas import JobAccepted, RerunRequest
from evas.auth import require_roles
from evas.db import get_session
from evas.enums import JobType, RunStatus, UserRole
from evas.jobs import enqueue
from evas.models import AiFrameFinding, AiRun, Checklist, Frame, HumanReview, User, Video

router = APIRouter(prefix="/ai", tags=["ai-monitor"])
_admin = require_roles(UserRole.admin)


def _duration_seconds(run: AiRun) -> float | None:
    if run.started_at is None:
        return None
    end = run.completed_at or datetime.datetime.now(datetime.UTC)
    return round((end - run.started_at).total_seconds(), 3)


@router.get("/runs")
def list_runs(
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
    status: RunStatus | None = None,
    client_id: uuid.UUID | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    date_from: datetime.datetime | None = None,
    date_to: datetime.datetime | None = None,
    has_issues: bool = False,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    frames_done = (
        select(func.count())
        .select_from(AiFrameFinding)
        .where(AiFrameFinding.ai_run_id == AiRun.id)
        .scalar_subquery()
    )
    frames_total = (
        select(func.count())
        .select_from(Frame)
        .where(Frame.video_id == AiRun.video_id)
        .scalar_subquery()
    )
    flagged = (
        select(func.count())
        .select_from(AiFrameFinding)
        .where(AiFrameFinding.ai_run_id == AiRun.id, AiFrameFinding.flagged)
        .scalar_subquery()
    )

    stmt = (
        select(
            AiRun,
            Video.external_ref,
            Video.client_id,
            Checklist.name.label("checklist_name"),
            Checklist.version.label("checklist_version"),
            Checklist.prompt_template.label("checklist_prompt"),
            frames_done.label("frames_done"),
            frames_total.label("frames_total"),
            flagged.label("flagged_frames"),
        )
        .join(Video, Video.id == AiRun.video_id)
        .join(Checklist, Checklist.id == AiRun.checklist_id)
        .where(Video.deleted_at.is_(None))
        .order_by(AiRun.created_at.desc())
    )
    if status is not None:
        stmt = stmt.where(AiRun.status == status)
    if client_id is not None:
        stmt = stmt.where(Video.client_id == client_id)
    if model is not None:
        stmt = stmt.where(AiRun.model == model)
    if prompt_version is not None:
        stmt = stmt.where(AiRun.prompt_version == prompt_version)
    if date_from is not None:
        stmt = stmt.where(AiRun.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(AiRun.created_at < date_to)
    if has_issues:
        stmt = stmt.where(or_(AiRun.status == RunStatus.failed, flagged > 0))
    stmt = stmt.limit(limit).offset(offset)

    out: list[dict[str, Any]] = []
    for row in session.execute(stmt).all():
        run, external_ref, cid, cl_name, cl_version, cl_prompt, done, total, flag = row
        out.append(
            {
                "id": str(run.id),
                "video_id": str(run.video_id),
                "external_ref": external_ref,
                "client_id": str(cid),
                "model": run.model,
                "prompt_version": run.prompt_version,
                "checklist_id": str(run.checklist_id),
                "checklist_name": cl_name,
                "checklist_version": int(cl_version),
                "prompt_is_custom": cl_prompt is not None,
                "status": run.status.value,
                "grade": float(run.grade) if run.grade is not None else None,
                "frames_done": int(done),
                "frames_total": int(total),
                "flagged_frames": int(flag),
                "tokens_in": run.tokens_in,
                "tokens_out": run.tokens_out,
                "cost_usd": float(run.cost_usd),
                "duration_seconds": _duration_seconds(run),
                "error": run.error,
                "started_at": run.started_at,
                "created_at": run.created_at,
            }
        )
    return out


@router.get("/stats")
def stats(
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
    date_from: datetime.datetime | None = None,
    date_to: datetime.datetime | None = None,
) -> dict[str, Any]:
    now = datetime.datetime.now(datetime.UTC)
    end = date_to or now
    start = date_from or (end - datetime.timedelta(days=7))
    hours = max((end - start).total_seconds() / 3600.0, 1e-9)

    # Only count runs whose video is still live (soft-deleted videos drop out).
    live_videos = select(Video.id).where(Video.deleted_at.is_(None)).scalar_subquery()

    def _by(group_col: Any) -> list[dict[str, Any]]:
        cols: list[Any] = [group_col] if group_col is not None else []
        run_rows = session.execute(
            select(
                *cols,
                func.count().label("runs"),
                func.count().filter(AiRun.status == RunStatus.completed).label("completed"),
                func.count().filter(AiRun.status == RunStatus.failed).label("failed"),
                func.coalesce(
                    func.avg(AiRun.cost_usd).filter(AiRun.status == RunStatus.completed), 0
                ).label("avg_cost"),
            )
            .where(
                AiRun.created_at >= start, AiRun.created_at < end, AiRun.video_id.in_(live_videos)
            )
            .group_by(*cols)
        ).all()
        # Confidence / flagged come from findings joined back to runs in range.
        find_rows = session.execute(
            select(
                *cols,
                func.coalesce(func.avg(AiFrameFinding.confidence), 0).label("avg_conf"),
                func.count().label("findings"),
                func.count().filter(AiFrameFinding.flagged).label("flagged"),
            )
            .select_from(AiFrameFinding)
            .join(AiRun, AiRun.id == AiFrameFinding.ai_run_id)
            .where(
                AiRun.created_at >= start, AiRun.created_at < end, AiRun.video_id.in_(live_videos)
            )
            .group_by(*cols)
        ).all()

        finds: dict[Any, Any] = {}
        for row in find_rows:
            key = row[0] if group_col is not None else "all"
            finds[key] = row

        result: list[dict[str, Any]] = []
        for row in run_rows:
            key = row[0] if group_col is not None else "all"
            f = finds.get(key)
            runs = int(row.runs)
            findings = int(f.findings) if f else 0
            flagged = int(f.flagged) if f else 0
            result.append(
                {
                    "key": key,
                    "runs": runs,
                    "completed": int(row.completed),
                    "failed": int(row.failed),
                    "error_rate": round(int(row.failed) / runs, 4) if runs else 0.0,
                    "throughput_per_hour": round(int(row.completed) / hours, 3),
                    "avg_cost_usd": round(float(row.avg_cost), 6),
                    "avg_confidence": round(float(f.avg_conf), 4) if f else None,
                    "flagged_rate": round(flagged / findings, 4) if findings else 0.0,
                }
            )
        return result

    overall = _by(None)
    return {
        "date_from": start,
        "date_to": end,
        "overall": overall[0] if overall else None,
        "by_model": _by(AiRun.model),
        "by_prompt_version": _by(AiRun.prompt_version),
    }


@router.get("/runs/{run_id}")
def get_run(
    run_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
) -> dict[str, Any]:
    run = session.get(AiRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    video = session.get(Video, run.video_id)
    assert video is not None  # FK guarantees it
    checklist = session.get(Checklist, run.checklist_id)

    rows = session.execute(
        select(AiFrameFinding, Frame)
        .join(Frame, Frame.id == AiFrameFinding.frame_id)
        .where(AiFrameFinding.ai_run_id == run.id)
        .order_by(Frame.frame_index)
    ).all()
    frames: list[dict[str, Any]] = []
    flagged_indices: list[int] = []
    for finding, frame in rows:
        if finding.flagged:
            flagged_indices.append(frame.frame_index)
        frames.append(
            {
                "frame_index": frame.frame_index,
                "timecode_label": frame.timecode_label,
                "timecode_seconds": float(frame.timecode_seconds),
                "image_url": None if frame.purged else storage.presign_get(frame.image_uri),
                "description": finding.description,
                "findings": finding.findings,
                "confidence": float(finding.confidence) if finding.confidence is not None else None,
                "flagged": finding.flagged,
            }
        )

    # Cross-link: AI vs latest non-QA human grade.
    human_grade = session.scalar(
        select(HumanReview.grade)
        .where(HumanReview.video_id == run.video_id, HumanReview.is_qa_review.is_(False))
        .order_by(HumanReview.reviewed_at.desc().nullslast())
        .limit(1)
    )
    ai_grade = float(run.grade) if run.grade is not None else None
    grade_gap = (
        abs(ai_grade - float(human_grade))
        if ai_grade is not None and human_grade is not None
        else None
    )
    frames_done = len(frames)

    return {
        "id": str(run.id),
        "video_id": str(run.video_id),
        "external_ref": video.external_ref,
        "client_id": str(video.client_id),
        "model": run.model,
        "prompt_version": run.prompt_version,
        "checklist_id": str(run.checklist_id),
        "checklist": {
            "id": str(run.checklist_id),
            "name": checklist.name if checklist else None,
            "version": checklist.version if checklist else None,
            "prompt_is_custom": bool(checklist and checklist.prompt_template),
            # item defs let the UI render each finding by its type
            "items": checklist.items if checklist else [],
        },
        "status": run.status.value,
        "grade": ai_grade,
        "summary": run.summary,
        "error": run.error,
        "duration_seconds": _duration_seconds(run),
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "cost": {
            "tokens_in": run.tokens_in,
            "tokens_out": run.tokens_out,
            "cost_usd": float(run.cost_usd),
            "cost_per_frame": round(float(run.cost_usd) / frames_done, 6) if frames_done else None,
        },
        "issues": {
            "flagged_frames": flagged_indices,
            "flagged_count": len(flagged_indices),
        },
        "human": {
            "grade": float(human_grade) if human_grade is not None else None,
            "grade_gap": round(grade_gap, 2) if grade_gap is not None else None,
        },
        "frames": frames,
    }


@router.post("/runs/{run_id}/rerun", response_model=JobAccepted, status_code=202)
def rerun(
    run_id: uuid.UUID,
    req: RerunRequest | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
) -> JobAccepted:
    """Queue a fresh ai_review for the run's video.

    Creates a new run (history preserved) — never edits the existing one. By
    default reuses the run's prompt_version and checklist; an optional body can
    re-run against a different prompt_version and/or checklist_id (the pipeline's
    _resolve_checklist honors payload.checklist_id).
    """
    run = session.get(AiRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    payload: dict[str, Any] = {"prompt_version": run.prompt_version}
    if req is not None and req.prompt_version is not None:
        payload["prompt_version"] = req.prompt_version
    if req is not None and req.checklist_id is not None:
        if session.get(Checklist, req.checklist_id) is None:
            raise HTTPException(status_code=404, detail="checklist not found")
        payload["checklist_id"] = str(req.checklist_id)
    job = enqueue(
        session,
        job_type=JobType.ai_review,
        video_id=run.video_id,
        payload=payload,
    )
    session.flush()
    return JobAccepted(job_id=job.id, job_type=job.job_type.value, status=job.status.value)
