"""ai_review step: one ai_runs pass over a video.

A re-review is always a NEW ai_runs row with new findings — AI results are never
overwritten (kickoff rule).

Payload (all optional):
  checklist_id    pin an exact checklist version (else the client's active one)
  prompt_version  override the frame prompt version (used by prompt A/B)
  target          "frame" (default) or "clip" for temporal/clip review
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
from evas.checklists import clip_items, compute_video_grade, frame_items
from evas.config import get_settings
from evas.enums import RunStatus, VideoStatus
from evas.models import (
    AiClipFinding,
    AiFrameFinding,
    AiRun,
    Checklist,
    Clip,
    Frame,
    ProcessingJob,
    Video,
)
from evas.storage import get_object_bytes
from evas.webhooks import EVENT_AI_REVIEWED, enqueue_notify


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _min_conf(findings: dict[str, Any]) -> float:
    confidences = [v["confidence"] for v in findings.values()]
    return min(confidences) if confidences else 0.0


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

    if job.payload.get("target") == "clip":
        _review_clips(session, job, video)
    else:
        _review_frames(session, job, video)


def _new_run(session: Session, video: Video, checklist: Checklist, reviewer: Any) -> AiRun:
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
    return run


def _review_frames(session: Session, job: ProcessingJob, video: Video) -> None:
    checklist = _resolve_checklist(session, video, job)
    items = frame_items(checklist.items)
    pv = job.payload.get("prompt_version")
    # A/B (explicit prompt_version) pins a versioned prompt file; otherwise use
    # the checklist's own UI-authored framing (or the default when unset).
    reviewer = ai.get_reviewer(
        prompt_version=pv, prompt_template=None if pv else checklist.prompt_template
    )
    threshold = get_settings().confidence_flag_threshold

    run = _new_run(session, video, checklist, reviewer)
    frames = session.scalars(
        select(Frame).where(Frame.video_id == video.id).order_by(Frame.frame_index)
    ).all()

    frame_findings: list[dict[str, Any]] = []
    tokens_in = tokens_out = 0
    cost = 0.0
    flagged_count = 0
    for frame in frames:
        result = reviewer.review_frame(get_object_bytes(frame.image_uri), items)
        min_conf = _min_conf(result.findings)
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

    run.grade = compute_video_grade(items, frame_findings, checklist.grading_mode)
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
        new_value={
            "grade": str(run.grade) if run.grade is not None else None,
            "frames": len(frames),
        },
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


def _review_clips(session: Session, job: ProcessingJob, video: Video) -> None:
    """Send each clip's ordered frame sequence to the model (clip-scoped items)."""
    checklist = _resolve_checklist(session, video, job)
    items = clip_items(checklist.items)
    if not items:
        raise ValueError("checklist has no clip-scoped items")
    pv = job.payload.get("prompt_version")
    reviewer = ai.get_reviewer(
        prompt_version=pv, prompt_template=None if pv else checklist.prompt_template
    )
    threshold = get_settings().confidence_flag_threshold

    clips = session.scalars(
        select(Clip).where(Clip.video_id == video.id).order_by(Clip.start_seconds)
    ).all()
    if not clips:
        raise ValueError("video has no clips to review")

    run = _new_run(session, video, checklist, reviewer)
    tokens_in = tokens_out = 0
    cost = 0.0
    flagged_count = 0
    for clip in clips:
        frames = session.scalars(
            select(Frame)
            .where(
                Frame.video_id == video.id,
                Frame.timecode_seconds >= clip.start_seconds,
                Frame.timecode_seconds <= clip.end_seconds,
            )
            .order_by(Frame.frame_index)
        ).all()
        images = [get_object_bytes(f.image_uri) for f in frames] or [b"\x00"]
        result = reviewer.review_clip(images, items)
        min_conf = _min_conf(result.findings)
        flagged = min_conf < threshold
        flagged_count += int(flagged)
        session.add(
            AiClipFinding(
                ai_run_id=run.id,
                clip_id=clip.id,
                description=result.description,
                findings=result.findings,
                confidence=Decimal(str(round(min_conf, 3))),
                flagged=flagged,
            )
        )
        tokens_in += result.tokens_in
        tokens_out += result.tokens_out
        cost += result.cost_usd

    run.summary = f"Reviewed {len(clips)} clip(s); {flagged_count} flagged for low confidence."
    run.tokens_in = tokens_in
    run.tokens_out = tokens_out
    run.cost_usd = Decimal(str(round(cost, 6)))
    run.status = RunStatus.completed
    run.completed_at = _now()
    write_audit(
        session,
        entity_type="ai_run",
        entity_id=run.id,
        action="clip_review_completed",
        new_value={"clips": len(clips)},
    )
