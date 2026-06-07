"""Auth: token issuance, role enforcement, and per-client tenancy scoping."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from evas.api.app import app
from evas.config import get_settings
from evas.db import session_scope
from evas.enums import UserRole
from evas.models import Client, User, Video

client = TestClient(app)


def _client_with_video(slug: str) -> tuple[uuid.UUID, uuid.UUID]:
    with session_scope() as s:
        c = Client(name=slug, slug=f"{slug}-{uuid.uuid4().hex[:6]}", sampling_config={})
        s.add(c)
        s.flush()
        v = Video(
            client_id=c.id,
            source_uri=f"s3://b/{slug}.mp4",
            file_hash=uuid.uuid4().hex,
        )
        s.add(v)
        s.flush()
        return c.id, v.id


def test_token_requires_bootstrap_config() -> None:
    # Default settings have no bootstrap_token -> 503.
    resp = client.post("/auth/token", json={"email": "x@y.co"})
    assert resp.status_code == 503


def test_token_minted_with_bootstrap(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "bootstrap_token", "s3cret")
    with session_scope() as s:
        u = User(email="admin@evas.co", full_name="A", role=UserRole.admin)
        s.add(u)

    bad = client.post(
        "/auth/token", json={"email": "admin@evas.co"}, headers={"X-Bootstrap-Token": "nope"}
    )
    assert bad.status_code == 401

    ok = client.post(
        "/auth/token", json={"email": "admin@evas.co"}, headers={"X-Bootstrap-Token": "s3cret"}
    )
    assert ok.status_code == 200
    assert ok.json()["token_type"] == "bearer"
    assert ok.json()["access_token"]


def test_client_viewer_is_scoped(make_user) -> None:
    client_a, video_a = _client_with_video("acme")
    client_b, video_b = _client_with_video("globex")
    _, token = make_user(role=UserRole.client_viewer, client_id=client_a)
    headers = {"Authorization": f"Bearer {token}"}

    # Listing only shows the viewer's own client (even when asking for B).
    listing = client.get("/videos", params={"client_id": str(client_b)}, headers=headers)
    assert listing.status_code == 200
    returned_clients = {row["client_id"] for row in listing.json()}
    assert returned_clients == {str(client_a)}

    # Cross-tenant detail access -> 404 (not 403, to avoid leaking existence).
    assert client.get(f"/videos/{video_b}", headers=headers).status_code == 404
    assert client.get(f"/videos/{video_a}", headers=headers).status_code == 200


def test_client_viewer_cannot_create_video(make_user) -> None:
    client_a, _ = _client_with_video("acme")
    _, token = make_user(role=UserRole.client_viewer, client_id=client_a)
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        "/videos", json={"client_id": str(client_a), "source_uri": "s3://b/x.mp4"}, headers=headers
    )
    assert resp.status_code == 403


def test_invalid_token_rejected() -> None:
    resp = client.get("/videos", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401
