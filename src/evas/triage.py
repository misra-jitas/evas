"""Frame triage: which frames a human should verify after an AI review.

Derived on demand from stored findings + config (no schema change). Three
signals by default — low certainty, AI-failed, and a random spot-check sample —
plus optional disagreement routing.

Config split (per the product decision):
- **Confidence threshold** is per-checklist: an optional per-item ``min_confidence``
  in the item JSON, else the global ``EVAS_CONFIDENCE_FLAG_THRESHOLD``. It versions
  with the questions.
- **Triage policy** (``sample_rate``, ``route_non_compliant``, ``route_on_disagreement``)
  is per-client, in ``client.sampling_config["triage"]``.
Both reuse existing JSON — no DDL.
"""

from __future__ import annotations

import hashlib
from typing import Any

from evas.checklists import _truthy, item_type
from evas.config import get_settings

DEFAULT_POLICY: dict[str, Any] = {
    "sample_rate": 0.1,
    "route_non_compliant": True,
    "route_on_disagreement": False,
}


def client_triage_policy(sampling_config: dict[str, Any] | None) -> dict[str, Any]:
    """Resolve a client's triage policy from its sampling_config, with defaults."""
    policy = dict(DEFAULT_POLICY)
    cfg = (sampling_config or {}).get("triage")
    if isinstance(cfg, dict):
        for k in DEFAULT_POLICY:
            if k in cfg:
                policy[k] = cfg[k]
    return policy


def item_min_confidence(item: dict[str, Any], default: float) -> float:
    """Per-item confidence threshold (items JSON), else the global default."""
    v = item.get("min_confidence")
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def frame_below_threshold(
    findings: dict[str, Any], items: list[dict[str, Any]], default_threshold: float
) -> bool:
    """True if any item's confidence is below its (per-item or global) threshold."""
    for it in items:
        entry = findings.get(it["key"]) or {}
        conf = entry.get("confidence")
        if conf is None:
            continue
        try:
            if float(conf) < item_min_confidence(it, default_threshold):
                return True
        except (TypeError, ValueError):
            continue
    return False


def _item_failed(item: dict[str, Any], entry: dict[str, Any]) -> bool:
    """Did the AI mark this single item non-compliant on this frame?"""
    itype = item_type(item)
    if itype == "boolean":
        return not _truthy(entry.get("value"))
    if itype == "category":
        compliant = item.get("compliant_values")
        if isinstance(compliant, list) and compliant:
            return entry.get("value") not in compliant
        return False
    if itype == "multi_boolean":
        values = entry.get("values") or {}
        subs = [o["key"] for o in item.get("options", []) if isinstance(o, dict) and o.get("key")]
        return any(not _truthy(values.get(s)) for s in subs) if subs else False
    if itype == "number":
        rng = item.get("compliant_range")
        if not isinstance(rng, list) or len(rng) != 2:
            return False
        v = entry.get("value")
        try:
            return v is None or not (float(rng[0]) <= float(v) <= float(rng[1]))
        except (TypeError, ValueError):
            return True
    return False  # text — never a failure


def frame_non_compliant(findings: dict[str, Any], items: list[dict[str, Any]]) -> bool:
    """True if the AI failed any weighted item on this frame."""
    for it in items:
        if float(it.get("weight", 1.0)) <= 0:
            continue
        if _item_failed(it, findings.get(it["key"]) or {}):
            return True
    return False


def _sampled(run_id: str, frame_index: int, rate: float) -> bool:
    """Deterministic spot-check: stable hash(run_id, frame) mapped to [0,1)."""
    if rate <= 0:
        return False
    h = hashlib.sha256(f"{run_id}:{frame_index}".encode()).digest()
    return (int.from_bytes(h[:4], "big") / 0xFFFFFFFF) < rate


def compute_triage(
    run_id: str,
    frames: list[dict[str, Any]],
    items: list[dict[str, Any]],
    policy: dict[str, Any],
    default_threshold: float | None = None,
) -> dict[str, Any]:
    """Return the triaged frame set + per-reason counts.

    ``frames`` items are dicts with ``frame_index`` and ``findings``.
    """
    threshold = default_threshold
    if threshold is None:
        threshold = get_settings().confidence_flag_threshold
    rate = float(policy.get("sample_rate", 0.0) or 0.0)
    route_fail = bool(policy.get("route_non_compliant", True))

    reasons: dict[int, list[str]] = {}
    counts = {"low_confidence": 0, "non_compliant": 0, "sample": 0}

    def add(idx: int, reason: str) -> None:
        reasons.setdefault(idx, [])
        if reason not in reasons[idx]:
            reasons[idx].append(reason)

    for f in frames:
        idx = f["frame_index"]
        findings = f.get("findings") or {}
        if frame_below_threshold(findings, items, threshold):
            add(idx, "low_confidence")
            counts["low_confidence"] += 1
        if route_fail and frame_non_compliant(findings, items):
            add(idx, "non_compliant")
            counts["non_compliant"] += 1
        if _sampled(run_id, idx, rate):
            add(idx, "sample")
            counts["sample"] += 1

    indices = sorted(reasons)
    return {
        "frame_indices": indices,
        "count": len(indices),
        "reasons": {str(k): v for k, v in reasons.items()},
        "counts": counts,
        "policy": {"sample_rate": rate, "route_non_compliant": route_fail, "threshold": threshold},
    }
