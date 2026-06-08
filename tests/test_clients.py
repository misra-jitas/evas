"""Client management: create / list / rename / delete, slug uniqueness, admin-only."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from evas.api.app import app
from evas.db import session_scope
from evas.enums import UserRole
from evas.models import Client

client = TestClient(app)


def _slug() -> str:
    return f"acme-{uuid.uuid4().hex[:6]}"


def test_create_list_get(auth_headers) -> None:
    slug = _slug()
    created = client.post("/clients", json={"name": "Acme", "slug": slug}, headers=auth_headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["slug"] == slug
    assert body["sampling_config"]["interval_seconds"] == 5  # default applied
    assert body["video_count"] == 0
    cid = body["id"]

    listing = client.get("/clients", headers=auth_headers).json()
    assert any(c["id"] == cid for c in listing)
    assert client.get(f"/clients/{cid}", headers=auth_headers).json()["name"] == "Acme"


def test_rename_and_edit(auth_headers) -> None:
    cid = client.post(
        "/clients", json={"name": "Old", "slug": _slug()}, headers=auth_headers
    ).json()["id"]
    resp = client.patch(
        f"/clients/{cid}",
        json={"name": "New Name", "frame_retention_days": 30},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"
    assert resp.json()["frame_retention_days"] == 30


def test_slug_conflict(auth_headers) -> None:
    slug = _slug()
    client.post("/clients", json={"name": "A", "slug": slug}, headers=auth_headers)
    dup = client.post("/clients", json={"name": "B", "slug": slug}, headers=auth_headers)
    assert dup.status_code == 409


def test_soft_delete(auth_headers) -> None:
    cid = client.post(
        "/clients", json={"name": "Doomed", "slug": _slug()}, headers=auth_headers
    ).json()["id"]
    assert client.delete(f"/clients/{cid}", headers=auth_headers).status_code == 204
    assert client.get(f"/clients/{cid}", headers=auth_headers).status_code == 404
    with session_scope() as s:
        slug = s.get(Client, uuid.UUID(cid)).slug
        assert s.get(Client, uuid.UUID(cid)).deleted_at is not None
    # slug stays reserved after soft delete (schema enforces a hard UNIQUE)
    assert (
        client.post(
            "/clients", json={"name": "Reuse", "slug": slug}, headers=auth_headers
        ).status_code
        == 409
    )


def test_requires_admin(make_user) -> None:
    _, token = make_user(role=UserRole.reviewer)
    resp = client.post(
        "/clients",
        json={"name": "X", "slug": _slug()},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
