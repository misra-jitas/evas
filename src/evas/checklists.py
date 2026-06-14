"""Checklist definitions and video-grade computation.

A checklist's `items` is a list of items. Every item has:
    {"key": str, "label": str, "type": ItemType, "weight": float,
     "scope": "frame" | "clip"}   # scope optional, defaults to "frame"

Item types and the AI-finding shape each one produces (all carry "confidence"):
    boolean       -> {"value": true|false, "confidence": 0.97}
    category      -> {"value": "<one option>", "confidence": ...}   item has "options": [str]
    multi_boolean -> {"values": {"<sub>": bool, ...}, "confidence"} ("options": [{"key","label"}])
    text          -> {"text": "...", "confidence": ...}            (informational, never graded)
    number        -> {"value": <number|null>, "confidence": ...}   item may have "min"/"max"

Grading: boolean and multi_boolean always contribute. category contributes only
when the item declares "compliant_values": [str]; number only when it declares
"compliant_range": [lo, hi]; text never contributes. A checklist with no
gradeable items yields a null grade.

Clip-scoped items are only evaluated on clips (temporal review, M3).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from evas.enums import GradingMode

ITEM_TYPES = frozenset({"boolean", "category", "multi_boolean", "text", "number"})


def item_type(item: dict[str, Any]) -> str:
    return str(item.get("type", "boolean"))


def validate_items(items: Any) -> list[dict[str, Any]]:
    """Validate a checklist `items` payload; return it unchanged or raise ValueError.

    Used by the checklist API before persisting UI-entered config.
    """
    if not isinstance(items, list) or not items:
        raise ValueError("items must be a non-empty list")
    seen: set[str] = set()
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError("each item must be an object")
        key = raw.get("key")
        if not isinstance(key, str) or not key:
            raise ValueError("each item needs a non-empty string 'key'")
        if key in seen:
            raise ValueError(f"duplicate item key: {key!r}")
        seen.add(key)
        itype = raw.get("type", "boolean")
        if itype not in ITEM_TYPES:
            raise ValueError(f"item {key!r}: unknown type {itype!r} (one of {sorted(ITEM_TYPES)})")
        if itype == "category":
            opts = raw.get("options")
            if not isinstance(opts, list) or not all(isinstance(o, str) and o for o in opts):
                raise ValueError(f"item {key!r}: category needs 'options' as a list of strings")
        if itype == "multi_boolean":
            opts = raw.get("options")
            if not isinstance(opts, list) or not opts:
                raise ValueError(f"item {key!r}: multi_boolean needs a non-empty 'options' list")
            for o in opts:
                if not isinstance(o, dict) or not isinstance(o.get("key"), str) or not o["key"]:
                    raise ValueError(f"item {key!r}: each multi_boolean option needs a 'key'")
        scope = raw.get("scope", "frame")
        if scope not in ("frame", "clip"):
            raise ValueError(f"item {key!r}: scope must be 'frame' or 'clip'")
    return items


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


def _in_range(value: Any, lo: Any, hi: Any) -> bool:
    try:
        x = Decimal(str(value))
        return Decimal(str(lo)) <= x <= Decimal(str(hi))
    except (TypeError, ValueError, ArithmeticError):
        return False


def _item_compliance(item: dict[str, Any], frame_findings: list[dict[str, Any]]) -> Decimal | None:
    """Fraction of frames (0–1) where this item is 'compliant', or None if the
    item is informational / has no compliance definition (and so is not graded).
    """
    key = item["key"]
    itype = item_type(item)
    n = len(frame_findings)

    def finding(ff: dict[str, Any]) -> dict[str, Any]:
        return ff.get(key) or {}

    if itype == "boolean":
        true_count = sum(1 for ff in frame_findings if _truthy(finding(ff).get("value")))
        return Decimal(true_count) / Decimal(n)

    if itype == "multi_boolean":
        subs = [o["key"] for o in item.get("options", []) if isinstance(o, dict) and o.get("key")]
        if not subs:
            return None
        total = Decimal(0)
        for sub in subs:
            tc = sum(
                1 for ff in frame_findings if _truthy((finding(ff).get("values") or {}).get(sub))
            )
            total += Decimal(tc) / Decimal(n)
        return total / Decimal(len(subs))

    if itype == "category":
        compliant = item.get("compliant_values")
        if not compliant:
            return None
        tc = sum(1 for ff in frame_findings if finding(ff).get("value") in compliant)
        return Decimal(tc) / Decimal(n)

    if itype == "number":
        rng = item.get("compliant_range")
        if not isinstance(rng, list) or len(rng) != 2:
            return None
        tc = sum(
            1
            for ff in frame_findings
            if finding(ff).get("value") is not None
            and _in_range(finding(ff)["value"], rng[0], rng[1])
        )
        return Decimal(tc) / Decimal(n)

    return None  # text — informational


def compute_video_grade(
    items: list[dict[str, Any]],
    frame_findings: list[dict[str, Any]],
    grading_mode: GradingMode,
) -> Decimal | None:
    """Compute a 0–10 video grade from per-frame findings of any item type.

    derived  → weighted mean of per-item compliance rates across all frames.
    holistic → unweighted mean of per-item compliance rates.

    Only gradeable items contribute (see module docstring). Returns None when
    there are no frames or no gradeable items.
    """
    if not frame_findings or not items:
        return None

    weighted_sum = Decimal(0)
    weight_total = Decimal(0)
    for item in items:
        compliance = _item_compliance(item, frame_findings)
        if compliance is None:
            continue
        weight = (
            Decimal(str(item.get("weight", 1.0)))
            if grading_mode is GradingMode.derived
            else Decimal(1)
        )
        weighted_sum += weight * compliance
        weight_total += weight

    if weight_total == 0:
        return None
    grade = (weighted_sum / weight_total) * Decimal(10)
    return grade.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
