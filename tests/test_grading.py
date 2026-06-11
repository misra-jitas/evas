"""Unit tests for video-grade computation."""

from __future__ import annotations

from decimal import Decimal

from evas.checklists import EXAMPLE_CHECKLIST_ITEMS, compute_video_grade, frame_items
from evas.enums import GradingMode

# Video grade is computed over frame-scoped items only (clip items reviewed separately).
ITEMS = frame_items(EXAMPLE_CHECKLIST_ITEMS)


def _ff(values: dict[str, bool]) -> dict:
    return {k: {"value": v, "confidence": 0.9} for k, v in values.items()}


def test_empty_returns_none() -> None:
    assert compute_video_grade(ITEMS, [], GradingMode.derived) is None


def test_all_true_is_ten() -> None:
    frames = [_ff({i["key"]: True for i in ITEMS})]
    assert compute_video_grade(ITEMS, frames, GradingMode.derived) == Decimal("10.00")


def test_all_false_is_zero() -> None:
    frames = [_ff({i["key"]: False for i in ITEMS})]
    assert compute_video_grade(ITEMS, frames, GradingMode.derived) == Decimal("0.00")


def test_derived_is_weighted() -> None:
    # holding_tool has weight 2.0; only it is true -> 2/5 of total weight -> 4.00
    frames = [_ff({i["key"]: (i["key"] == "holding_tool") for i in ITEMS})]
    assert compute_video_grade(ITEMS, frames, GradingMode.derived) == Decimal("4.00")


def test_holistic_is_unweighted() -> None:
    frames = [_ff({i["key"]: (i["key"] == "holding_tool") for i in ITEMS})]
    # unweighted: 1 of 4 items true -> 2.50
    assert compute_video_grade(ITEMS, frames, GradingMode.holistic) == Decimal("2.50")
