"""Multi-type checklist items: validation, normalization, grading, and the
checklist-config API (UI-editable items + prompt_template, versioned)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from evas.ai import _normalize_findings
from evas.api.app import app
from evas.checklists import compute_video_grade, validate_items
from evas.enums import GradingMode, UserRole

client = TestClient(app)

TROUT_ITEMS = [
    {"key": "is_fish", "label": "A real fish is visible", "type": "boolean", "weight": 1.0},
    {
        "key": "species",
        "label": "Species",
        "type": "category",
        "options": ["trout", "salmon", "bass"],
        "compliant_values": ["trout"],
        "weight": 2.0,
    },
    {
        "key": "markings",
        "label": "Visible markings",
        "type": "multi_boolean",
        "options": [
            {"key": "spots", "label": "Spots"},
            {"key": "adipose_fin", "label": "Adipose fin"},
        ],
        "weight": 1.0,
    },
    {"key": "caption", "label": "What is shown", "type": "text"},
    {"key": "length_cm", "label": "Estimated length", "type": "number", "min": 0, "max": 120},
]


# ---- validation ----
def test_validate_rejects_bad_shapes() -> None:
    with pytest.raises(ValueError):
        validate_items([])
    with pytest.raises(ValueError):
        validate_items([{"key": "a", "type": "frobnicate"}])
    with pytest.raises(ValueError):
        validate_items([{"key": "a", "type": "category"}])  # no options
    with pytest.raises(ValueError):
        validate_items([{"key": "x"}, {"key": "x"}])  # duplicate keys


def test_validate_accepts_trout() -> None:
    assert validate_items(TROUT_ITEMS) is TROUT_ITEMS


# ---- normalization (tolerant coercion to canonical per-type shapes) ----
def test_normalize_each_type() -> None:
    raw = {
        "is_fish": {"value": True, "confidence": 0.9},
        "species": {"value": "trout", "confidence": 0.8},
        "markings": {"values": {"spots": True, "adipose_fin": False}, "confidence": 0.7},
        "caption": {"text": "a speckled fish in a net", "confidence": 0.6},
        "length_cm": {"value": "33.5", "confidence": 0.5},
    }
    out = _normalize_findings(raw, TROUT_ITEMS)
    assert out["is_fish"] == {"value": True, "confidence": 0.9}
    assert out["species"] == {"value": "trout", "confidence": 0.8}
    assert out["markings"]["values"] == {"spots": True, "adipose_fin": False}
    assert out["caption"]["text"] == "a speckled fish in a net"
    assert out["length_cm"]["value"] == 33.5


def test_normalize_rejects_out_of_vocab_category() -> None:
    out = _normalize_findings({"species": {"value": "marlin", "confidence": 1.0}}, TROUT_ITEMS)
    assert out["species"]["value"] is None  # not in options
    # missing keys still get safe defaults
    assert out["is_fish"] == {"value": False, "confidence": 0.0}
    assert out["length_cm"]["value"] is None


# ---- grading across types ----
def _frame(species: str, spots: bool, fin: bool, length: float) -> dict:
    return _normalize_findings(
        {
            "is_fish": {"value": True, "confidence": 1.0},
            "species": {"value": species, "confidence": 1.0},
            "markings": {"values": {"spots": spots, "adipose_fin": fin}, "confidence": 1.0},
            "caption": {"text": "x", "confidence": 1.0},
            "length_cm": {"value": length, "confidence": 1.0},
        },
        TROUT_ITEMS,
    )


def test_grade_mixes_types_and_excludes_text() -> None:
    # All-compliant frame: is_fish true, species trout (compliant), both markings true.
    grade = compute_video_grade(TROUT_ITEMS, [_frame("trout", True, True, 30)], GradingMode.derived)
    assert grade == Decimal("10.00")
    # species not trout -> its 2.0-weighted item drops to 0; markings half.
    g2 = compute_video_grade(TROUT_ITEMS, [_frame("salmon", True, False, 30)], GradingMode.derived)
    # weights: is_fish 1*1.0 + species 2*0 + markings 1*0.5 = 1.5 ; total weight 4 -> 3.75
    assert g2 == Decimal("3.75")


def test_grade_none_when_only_informational() -> None:
    items = [{"key": "caption", "label": "x", "type": "text"}]
    ff = _normalize_findings({"caption": {"text": "hi", "confidence": 1.0}}, items)
    assert compute_video_grade(items, [ff], GradingMode.derived) is None


# ---- checklist-config API ----
def _make_client(headers) -> str:
    r = client.post(
        "/clients",
        json={"name": "Fishery", "slug": f"fish-{uuid.uuid4().hex[:6]}"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_save_and_version_checklist(auth_headers) -> None:
    cid = _make_client(auth_headers)
    body = {
        "name": "trout_v1",
        "items": TROUT_ITEMS,
        "prompt_template": "You are a fish-identification auditor.",
        "grading_mode": "derived",
    }
    r1 = client.post(f"/clients/{cid}/checklists", json=body, headers=auth_headers)
    assert r1.status_code == 201, r1.text
    assert r1.json()["version"] == 1
    assert r1.json()["is_active"] is True

    # Saving again bumps the version and deactivates the prior one.
    r2 = client.post(f"/clients/{cid}/checklists", json=body, headers=auth_headers)
    assert r2.json()["version"] == 2

    active = client.get(f"/clients/{cid}/checklists/active", headers=auth_headers)
    assert active.status_code == 200
    assert active.json()["version"] == 2
    assert active.json()["prompt_template"].startswith("You are a fish")

    listing = client.get(f"/clients/{cid}/checklists", headers=auth_headers)
    assert {c["version"] for c in listing.json()} == {1, 2}


def test_save_rejects_bad_items(auth_headers) -> None:
    cid = _make_client(auth_headers)
    r = client.post(
        f"/clients/{cid}/checklists",
        json={"name": "bad", "items": [{"key": "s", "type": "category"}]},
        headers=auth_headers,
    )
    assert r.status_code == 422


def test_checklist_routes_admin_only(auth_headers, make_user) -> None:
    cid = _make_client(auth_headers)
    _, reviewer_token = make_user(role=UserRole.reviewer)
    r = client.get(
        f"/clients/{cid}/checklists",
        headers={"Authorization": f"Bearer {reviewer_token}"},
    )
    assert r.status_code == 403
