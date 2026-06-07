"""ai_review step: one ai_runs pass over a video's frames.

A re-review is always a NEW ai_runs row with new ai_frame_findings — AI results
are never overwritten (kickoff rule).

Payload (optional): {checklist_id} to pin an exact checklist version; otherwise
the client's active checklist is used.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from evas import ai
from evas.audit import record_status_change, write_audit
from evas.checklists import compute_video_grade
from evas.config import get_settings
from evas.enums import RunStatus, VideoStatus
from evas.models import AiFrameFinding, AiRun, Checklist, Frame, ProcessingJob, Video
from evas.storage import get_object_bytes
from evas.webhooks import EVENT_AI_REVIEWED, enqueue_notify


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _resolve_checklist(session: Session, video: Video, job: ProcessingJob) -> Checklist:
    pinned = job.payload.get("checklist_id")
    if pinned:
        checklist = session.get(Checklist, uuid.UUID(str(pinned)))
        if checklist is None:
            raise ValueError(f"checklist {pinned} not found")
        return checklist
    checklist = session.scalars(
        select(Checklist)
        .where(Checklist.client_id == video.client_id, Checklist.is_active.is_(True))
        .order_by(Checklist.version.desc())
    ).first()
    if checklist is None:
        raise ValueError(f"no active checklist for client {video.client_id}")
    return checklist


def handle_ai_review(session: Session, job: ProcessingJob) -> None:
    if job.video_id is None:
        raise ValueError("ai_review job has no video_id")
    video = session.get(Video, job.video_id)
    if video is None:
        raise ValueError(f"video {job.video_id} not found")

    checklist = _resolve_checklist(session, video, job)
    items = checklist.items
    reviewer = ai.AiReviewer()
    settings = get_settings()
    threshold = settings.confidence_flag_threshold

    run = AiRun(
        video_id=video.id,
        checklist_id=checklist.id,
        model=reviewer.model,
        prompt_version=reviewer.prompt_version,
        status=RunStatus.running,
        started_at=_now(),
    )
    session.add(run)
    session.flush()

    frames = session.scalars(
        select(Frame).where(Frame.video_id == video.id).order_by(Frame.frame_index)
    ).all()

    frame_findings: list[dict[str, Any]] = []
    tokens_in = tokens_out = 0
    cost = 0.0
    flagged_count = 0
    for frame in frames:
        image = get_object_bytes(frame.image_uri)
        result = reviewer.review_frame(image, items)
        confidences = [v["confidence"] for v in result.findings.values()] or [0.0]
        min_conf = min(confidences)
        flagged = min_conf < threshold
        flagged_count += int(flagged)
        session.add(
            AiFrameFinding(
                ai_run_id=run.id,
                frame_id=frame.id,
                description=result.description,
                findings=result.findings,
                confidence=Decimal(str(round(min_conf, 3))),
                flagged=flagged,
            )
        )
        frame_findings.append(result.findings)
        tokens_in += result.tokens_in
        tokens_out += result.tokens_out
        cost += result.cost_usd

    grade = compute_video_grade(items, frame_findings, checklist.grading_mode)
    run.grade = grade
    run.summary = f"Reviewed {len(frames)} frame(s); {flagged_count} flagged for low confidence."
    run.tokens_in = tokens_in
    run.tokens_out = tokens_out
    run.cost_usd = Decimal(str(round(cost, 6)))
    run.status = RunStatus.completed
    run.completed_at = _now()

    write_audit(
        session,
        entity_type="ai_run",
        entity_id=run.id,
        action="completed",
        new_value={"grade": str(grade) if grade is not None else None, "frames": len(frames)},
    )

    old = video.status.value
    video.status = VideoStatus.ai_reviewed
    record_status_change(
        session,
        entity_type="video",
        entity_id=video.id,
        old_status=old,
        new_status=VideoStatus.ai_reviewed.value,
    )
    enqueue_notify(session, video.id, EVENT_AI_REVIEWED)
