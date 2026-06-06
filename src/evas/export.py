"""Findings export: build one JSON document per video (latest completed run)."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from evas.config import get_settings
from evas.enums import RunStatus
from evas.models import AiFrameFinding, AiRun, Frame, Video


def latest_completed_run(session: Session, video_id: uuid.UUID) -> AiRun | None:
    return session.scalars(
        select(AiRun)
        .where(AiRun.video_id == video_id, AiRun.status == RunStatus.completed)
        .order_by(AiRun.completed_at.desc())
        .limit(1)
    ).first()


def build_export(session: Session, video_id: uuid.UUID) -> dict[str, Any]:
    """Assemble the export document for a video's latest completed AI run."""
    video = session.get(Video, video_id)
    if video is None or video.deleted_at is not None:
        raise LookupError(f"video {video_id} not found")

    run = latest_completed_run(session, video_id)
    doc: dict[str, Any] = {
        "video": {
            "id": str(video.id),
            "client_id": str(video.client_id),
            "external_ref": video.external_ref,
            "original_filename": video.original_filename,
            "source_uri": video.source_uri,
            "status": video.status.value,
            "duration_seconds": float(video.duration_seconds)
            if video.duration_seconds is not None
            else None,
        },
        "ai_run": None,
        "frames": [],
    }
    if run is None:
        return doc

    doc["ai_run"] = {
        "id": str(run.id),
        "model": run.model,
        "prompt_version": run.prompt_version,
        "checklist_id": str(run.checklist_id),
        "grade": float(run.grade) if run.grade is not None else None,
        "summary": run.summary,
        "tokens_in": run.tokens_in,
        "tokens_out": run.tokens_out,
        "cost_usd": float(run.cost_usd),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }

    rows = session.execute(
        select(Frame, AiFrameFinding)
        .join(AiFrameFinding, AiFrameFinding.frame_id == Frame.id)
        .where(AiFrameFinding.ai_run_id == run.id)
        .order_by(Frame.frame_index)
    ).all()
    for frame, finding in rows:
        doc["frames"].append(
            {
                "frame_index": frame.frame_index,
                "timecode_seconds": float(frame.timecode_seconds),
                "timecode_label": frame.timecode_label,
                "image_uri": frame.image_uri,
                "description": finding.description,
                "findings": finding.findings,
                "confidence": float(finding.confidence) if finding.confidence is not None else None,
                "flagged": finding.flagged,
            }
        )
    return doc


def export_to_file(session: Session, video_id: uuid.UUID, out_dir: str | None = None) -> str:
    """Write the export document to <export_dir>/<video_id>.json and return its path."""
    out_dir = out_dir or get_settings().export_dir
    os.makedirs(out_dir, exist_ok=True)
    doc = build_export(session, video_id)
    path = os.path.join(out_dir, f"{video_id}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
    return path
