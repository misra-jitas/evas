"""Checklist definitions and video-grade computation.

A checklist's `items` is a list of:
    {"key": str, "label": str, "type": "boolean", "weight": float,
     "scope": "frame" | "clip"}   # scope optional, defaults to "frame"

Per-frame AI findings mirror the item keys:
    {"two_hands": {"value": true, "confidence": 0.97}, ...}

Clip-scoped items are only evaluated on clips (temporal review, M3).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from evas.enums import GradingMode

# Milestone-1 example checklist (workstation safety/compliance).
# Frame-scoped items are evaluated per still frame; clip-scoped items (M3) ask
# action-level questions over a frame sequence.
EXAMPLE_CHECKLIST_NAME = "workstation_v1"
EXAMPLE_CHECKLIST_ITEMS: list[dict[str, Any]] = [
    {"key": "two_hands", "label": "Two hands visible", "type": "boolean", "weight": 1.0},
    {"key": "holding_tool", "label": "Hand holding a tool", "type": "boolean", "weight": 2.0},
    {"key": "at_workstation", "label": "Person at workstation", "type": "boolean", "weight": 1.0},
    {"key": "holding_broom", "label": "Holding a broom", "type": "boolean", "weight": 1.0},
    {
        "key": "is_sweeping",
        "label": "Person is actively sweeping",
        "type": "boolean",
        "weight": 1.0,
        "scope": "clip",
    },
]


def item_scope(item: dict[str, Any]) -> str:
    return str(item.get("scope", "frame"))


def frame_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [it for it in items if item_scope(it) == "frame"]


def clip_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [it for it in items if item_scope(it) == "clip"]


def item_keys(items: list[dict[str, Any]]) -> list[str]:
    return [item["key"] for item in items]


def _truthy(value: Any) -> bool:
    return value is True or value == 1 or (isinstance(value, str) and value.lower() == "true")


def compute_video_grade(
    items: list[dict[str, Any]],
    frame_findings: list[dict[str, Any]],
    grading_mode: GradingMode,
) -> Decimal | None:
    """Compute a 0–10 video grade from per-frame boolean findings.

    derived  → weighted mean of per-item compliance rates across all frames.
    holistic → unweighted mean of per-item compliance rates.

    Returns None when there are no frames to grade.
    """
    if not frame_findings or not items:
        return None

    n = len(frame_findings)
    weighted_sum = Decimal(0)
    weight_total = Decimal(0)
    for item in items:
        key = item["key"]
        weight = (
            Decimal(str(item.get("weight", 1.0)))
            if grading_mode is GradingMode.derived
            else Decimal(1)
        )
        true_count = sum(1 for ff in frame_findings if _truthy((ff.get(key) or {}).get("value")))
        compliance = Decimal(true_count) / Decimal(n)
        weighted_sum += weight * compliance
        weight_total += weight

    if weight_total == 0:
        return None
    grade = (weighted_sum / weight_total) * Decimal(10)
    return grade.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
