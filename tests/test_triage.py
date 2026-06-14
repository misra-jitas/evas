"""Frame triage: per-item thresholds, non-compliance, sampling, policy."""

from __future__ import annotations

from evas.triage import (
    client_triage_policy,
    compute_triage,
    frame_below_threshold,
    frame_non_compliant,
)

ITEMS = [
    {"key": "two_hands", "type": "boolean", "weight": 1.0},
    {
        "key": "species",
        "type": "category",
        "options": ["trout", "salmon"],
        "compliant_values": ["trout"],
        "weight": 2.0,
    },
    {"key": "strict", "type": "boolean", "weight": 1.0, "min_confidence": 0.95},
    {"key": "caption", "type": "text"},
]


def test_per_item_threshold() -> None:
    # strict item demands 0.95; 0.9 is below it even though above the 0.75 global.
    findings = {"strict": {"value": True, "confidence": 0.9}}
    assert frame_below_threshold(findings, ITEMS, 0.75) is True
    # a normal item at 0.9 is fine under the 0.75 global.
    assert (
        frame_below_threshold({"two_hands": {"value": True, "confidence": 0.9}}, ITEMS, 0.75)
        is False
    )


def test_non_compliant_by_type() -> None:
    # boolean false (weighted) -> failed
    assert frame_non_compliant({"two_hands": {"value": False, "confidence": 1.0}}, ITEMS) is True
    # category not in compliant_values -> failed
    assert frame_non_compliant({"species": {"value": "salmon", "confidence": 1.0}}, ITEMS) is True
    # everything compliant -> not failed
    ok = {"two_hands": {"value": True}, "species": {"value": "trout"}, "strict": {"value": True}}
    assert frame_non_compliant(ok, ITEMS) is False


def test_compute_triage_combines_signals() -> None:
    frames = [
        {
            "frame_index": 0,
            "findings": {
                "two_hands": {"value": True, "confidence": 0.99},
                "species": {"value": "trout", "confidence": 0.99},
                "strict": {"value": True, "confidence": 0.99},
            },
        },
        {
            "frame_index": 1,
            "findings": {"two_hands": {"value": False, "confidence": 0.99}},
        },  # AI-failed
        {
            "frame_index": 2,
            "findings": {"strict": {"value": True, "confidence": 0.5}},
        },  # low conf (per-item)
    ]
    policy = {"sample_rate": 0.0, "route_non_compliant": True}
    t = compute_triage("run-x", frames, ITEMS, policy, default_threshold=0.75)
    assert 1 in t["frame_indices"] and 2 in t["frame_indices"]
    assert t["counts"]["non_compliant"] >= 1 and t["counts"]["low_confidence"] >= 1
    # frame 0 is clean
    assert 0 not in t["frame_indices"]


def test_sampling_is_deterministic() -> None:
    frames = [
        {"frame_index": i, "findings": {"two_hands": {"value": True, "confidence": 1.0}}}
        for i in range(50)
    ]
    a = compute_triage(
        "run-1", frames, ITEMS, {"sample_rate": 1.0, "route_non_compliant": False}, 0.75
    )
    b = compute_triage(
        "run-1", frames, ITEMS, {"sample_rate": 1.0, "route_non_compliant": False}, 0.75
    )
    assert a["frame_indices"] == b["frame_indices"]  # stable
    assert a["counts"]["sample"] == 50  # rate 1.0 catches all


def test_policy_defaults_and_overrides() -> None:
    assert client_triage_policy(None)["route_non_compliant"] is True
    pol = client_triage_policy({"triage": {"sample_rate": 0.25, "route_non_compliant": False}})
    assert pol["sample_rate"] == 0.25 and pol["route_non_compliant"] is False
