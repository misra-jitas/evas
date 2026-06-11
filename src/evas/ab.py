"""Prompt A/B testing: run two prompt versions over a video set and compare.

Each version's pass is a separate ai_runs row (AI history is never overwritten).
Comparison uses the latest human grade as ground truth where available.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from evas.enums import JobType, RunStatus
from evas.jobs import enqueue
from evas.models import AiFrameFinding, AiRun, HumanReview


def enqueue_ab_runs(
    session: Session,
    video_ids: list[uuid.UUID],
    prompt_version_a: str,
    prompt_version_b: str,
) -> int:
    """Queue a frame ai_review per (video, version). Returns jobs enqueued."""
    count = 0
    for video_id in video_ids:
        for version in (prompt_version_a, prompt_version_b):
            enqueue(
                session,
                job_type=JobType.ai_review,
                video_id=video_id,
                payload={"prompt_version": version},
            )
            count += 1
    return count


def _latest_run(session: Session, video_id: uuid.UUID, prompt_version: str) -> AiRun | None:
    return session.scalars(
        select(AiRun)
        .where(
            AiRun.video_id == video_id,
            AiRun.prompt_version == prompt_version,
            AiRun.status == RunStatus.completed,
        )
        .order_by(AiRun.completed_at.desc())
    ).first()


def _human_grade(session: Session, video_id: uuid.UUID) -> float | None:
    hr = session.scalars(
        select(HumanReview)
        .where(
            HumanReview.video_id == video_id,
            HumanReview.is_qa_review.is_(False),
            HumanReview.grade.is_not(None),
        )
        .order_by(HumanReview.reviewed_at.desc())
    ).first()
    return float(hr.grade) if hr and hr.grade is not None else None


def _findings_by_frame(session: Session, run_id: uuid.UUID) -> dict[uuid.UUID, dict[str, Any]]:
    rows = session.scalars(select(AiFrameFinding).where(AiFrameFinding.ai_run_id == run_id)).all()
    return {r.frame_id: r.findings for r in rows}


def compare(
    session: Session,
    video_ids: list[uuid.UUID],
    prompt_version_a: str,
    prompt_version_b: str,
) -> dict[str, Any]:
    """Build a comparison report between two prompt versions over the video set."""
    per_video: list[dict[str, Any]] = []
    cost_a = cost_b = 0.0
    abs_err_a: list[float] = []
    abs_err_b: list[float] = []
    item_disagreements: dict[str, int] = {}
    item_totals: dict[str, int] = {}

    for video_id in video_ids:
        run_a = _latest_run(session, video_id, prompt_version_a)
        run_b = _latest_run(session, video_id, prompt_version_b)
        if run_a is None or run_b is None:
            per_video.append({"video_id": str(video_id), "complete": False})
            continue

        grade_a = float(run_a.grade) if run_a.grade is not None else None
        grade_b = float(run_b.grade) if run_b.grade is not None else None
        human = _human_grade(session, video_id)
        cost_a += float(run_a.cost_usd)
        cost_b += float(run_b.cost_usd)
        if human is not None and grade_a is not None:
            abs_err_a.append(abs(grade_a - human))
        if human is not None and grade_b is not None:
            abs_err_b.append(abs(grade_b - human))

        # Per-item disagreement across shared frames.
        fa = _findings_by_frame(session, run_a.id)
        fb = _findings_by_frame(session, run_b.id)
        disagree = 0
        for frame_id in fa.keys() & fb.keys():
            for key in fa[frame_id].keys() | fb[frame_id].keys():
                va = bool((fa[frame_id].get(key) or {}).get("value"))
                vb = bool((fb[frame_id].get(key) or {}).get("value"))
                item_totals[key] = item_totals.get(key, 0) + 1
                if va != vb:
                    item_disagreements[key] = item_disagreements.get(key, 0) + 1
                    disagree += 1

        per_video.append(
            {
                "video_id": str(video_id),
                "complete": True,
                "grade_a": grade_a,
                "grade_b": grade_b,
                "grade_delta": None if grade_a is None or grade_b is None else grade_b - grade_a,
                "human_grade": human,
                "abs_err_a": None if human is None or grade_a is None else abs(grade_a - human),
                "abs_err_b": None if human is None or grade_b is None else abs(grade_b - human),
                "frame_disagreements": disagree,
            }
        )

    mae_a = sum(abs_err_a) / len(abs_err_a) if abs_err_a else None
    mae_b = sum(abs_err_b) / len(abs_err_b) if abs_err_b else None

    recommendation = _recommend(prompt_version_a, prompt_version_b, mae_a, mae_b, cost_a, cost_b)

    return {
        "prompt_version_a": prompt_version_a,
        "prompt_version_b": prompt_version_b,
        "videos": per_video,
        "totals": {
            "cost_a": round(cost_a, 6),
            "cost_b": round(cost_b, 6),
            "mae_vs_human_a": mae_a,
            "mae_vs_human_b": mae_b,
        },
        "item_disagreements": {
            key: {"disagreements": item_disagreements.get(key, 0), "total": item_totals[key]}
            for key in sorted(item_totals)
        },
        "recommendation": recommendation,
    }


def _recommend(
    version_a: str,
    version_b: str,
    mae_a: float | None,
    mae_b: float | None,
    cost_a: float,
    cost_b: float,
) -> dict[str, Any]:
    # Prefer the version closer to human ground truth; tiebreak on lower cost.
    if mae_a is not None and mae_b is not None and mae_a != mae_b:
        winner = version_a if mae_a < mae_b else version_b
        reason = "lower mean absolute error vs human grades"
    elif cost_a != cost_b:
        winner = version_a if cost_a < cost_b else version_b
        reason = "lower cost (accuracy tied or no human ground truth)"
    else:
        winner = version_a
        reason = "tie; defaulting to version A"
    return {"promote": winner, "reason": reason}
