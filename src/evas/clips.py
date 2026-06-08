"""Clip (temporal segment) helpers: manual and automatic segmentation.

Auto-segmentation splits a video into clips wherever the AI frame findings
change between consecutive frames — each run of frames with an identical
boolean finding signature becomes one clip.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from evas.enums import RunStatus
from evas.export import latest_completed_run
from evas.models import AiFrameFinding, Clip, Frame

AUTO_LABEL = "auto"


def _signature(findings: dict[str, Any]) -> tuple[tuple[str, bool], ...]:
    return tuple(sorted((k, bool(v.get("value"))) for k, v in findings.items()))


def create_clip(
    session: Session,
    video_id: uuid.UUID,
    start_seconds: float,
    end_seconds: float,
    label: str | None = None,
) -> Clip:
    """Manually create a clip. Does not commit."""
    if end_seconds < start_seconds:
        raise ValueError("end_seconds must be >= start_seconds")
    clip = Clip(
        video_id=video_id,
        start_seconds=Decimal(str(round(start_seconds, 3))),
        end_seconds=Decimal(str(round(end_seconds, 3))),
        label=label,
    )
    session.add(clip)
    session.flush()
    return clip


def auto_segment(session: Session, video_id: uuid.UUID) -> list[Clip]:
    """Regenerate auto clips from the latest completed frame review.

    Replaces previously auto-generated clips (label == AUTO_LABEL); manual clips
    are left untouched. Returns the created clips.
    """
    run = latest_completed_run(session, video_id)
    if run is None or run.status != RunStatus.completed:
        raise ValueError("no completed AI run to segment from")

    rows = session.execute(
        select(Frame, AiFrameFinding)
        .join(AiFrameFinding, AiFrameFinding.frame_id == Frame.id)
        .where(AiFrameFinding.ai_run_id == run.id)
        .order_by(Frame.frame_index)
    ).all()
    if not rows:
        return []

    # Drop previous auto clips so re-running is idempotent.
    for old in session.scalars(
        select(Clip).where(Clip.video_id == video_id, Clip.label == AUTO_LABEL)
    ).all():
        session.delete(old)
    session.flush()

    clips: list[Clip] = []
    seg_start = rows[0][0]
    prev = rows[0][0]
    prev_sig = _signature(rows[0][1].findings)
    for frame, finding in rows[1:]:
        sig = _signature(finding.findings)
        if sig != prev_sig:
            clips.append(
                create_clip(
                    session,
                    video_id,
                    float(seg_start.timecode_seconds),
                    float(prev.timecode_seconds),
                    AUTO_LABEL,
                )
            )
            seg_start = frame
            prev_sig = sig
        prev = frame
    clips.append(
        create_clip(
            session,
            video_id,
            float(seg_start.timecode_seconds),
            float(prev.timecode_seconds),
            AUTO_LABEL,
        )
    )
    return clips
