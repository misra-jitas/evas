"""API tests via Starlette TestClient against the real test DB (with auth)."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from evas import worker
from evas.api.app import app
from evas.checklists import EXAMPLE_CHECKLIST_ITEMS, EXAMPLE_CHECKLIST_NAME
from evas.db import session_scope
from evas.models import Checklist, Client, Video

client = TestClient(app)


def _seed_client() -> uuid.UUID:
    with session_scope() as s:
        c = Client(
            name="Acme",
            slug=f"acme-{uuid.uuid4().hex[:8]}",
            sampling_config={"interval_seconds": 1, "max_frames": 2, "frame_width": 160},
        )
        s.add(c)
        s.flush()
        s.add(
            Checklist(
                client_id=c.id,
                name=EXAMPLE_CHECKLIST_NAME,
                version=1,
                items=EXAMPLE_CHECKLIST_ITEMS,
                is_active=True,
            )
        )
        return c.id


def test_health_is_public() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_videos_requires_auth() -> None:
    assert client.get("/videos").status_code == 401  # no bearer token


def test_create_video_enqueues_job(auth_headers) -> None:
    client_id = _seed_client()
    resp = client.post(
        "/videos",
        json={"client_id": str(client_id), "source_uri": "s3://evas-videos/a/b.mp4"},
        headers=auth_headers,
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["job_type"] == "ingest"
    assert body["status"] == "queued"

    job = client.get(f"/jobs/{body['job_id']}", headers=auth_headers)
    assert job.status_code == 200
    assert job.json()["job_type"] == "ingest"


def test_list_detail_export(auth_headers, fake_s3, fake_ai, sample_video_bytes) -> None:
    client_id = _seed_client()
    source_uri = "s3://evas-videos/a/full.mp4"
    fake_s3.put(source_uri, sample_video_bytes)

    resp = client.post(
        "/videos",
        json={"client_id": str(client_id), "source_uri": source_uri},
        headers=auth_headers,
    )
    assert resp.status_code == 202
    while worker.run_once():
        pass

    with session_scope() as s:
        video_id = s.scalars(select(Video.id)).one()

    listing = client.get("/videos", params={"client_id": str(client_id)}, headers=auth_headers)
    assert listing.status_code == 200
    rows = listing.json()
    assert len(rows) == 1
    assert rows[0]["status"] == "ai_reviewed"
    assert rows[0]["ai_grade"] is not None

    detail = client.get(f"/videos/{video_id}", headers=auth_headers)
    assert detail.status_code == 200
    d = detail.json()
    assert d["latest_ai_run"]["grade"] is not None
    assert len(d["frames"]) == 2
    assert d["frames"][0]["findings"] is not None

    export = client.get(f"/videos/{video_id}/export", headers=auth_headers)
    assert export.status_code == 200
    ex = export.json()
    assert ex["ai_run"]["grade"] is not None
    assert len(ex["frames"]) == 2


def test_video_media_and_frame_image_urls(
    auth_headers, fake_s3, fake_ai, sample_video_bytes
) -> None:
    """Reviewer can fetch a presigned video URL; frames carry presigned image URLs."""
    client_id = _seed_client()
    source_uri = "s3://evas-videos/a/watch.mp4"
    fake_s3.put(source_uri, sample_video_bytes)
    resp = client.post(
        "/videos",
        json={"client_id": str(client_id), "source_uri": source_uri},
        headers=auth_headers,
    )
    assert resp.status_code == 202
    while worker.run_once():
        pass
    with session_scope() as s:
        video_id = s.scalars(select(Video.id)).one()

    media = client.get(f"/videos/{video_id}/media", headers=auth_headers)
    assert media.status_code == 200
    assert media.json()["url"].startswith("https://fake-s3.local/")

    detail = client.get(f"/videos/{video_id}", headers=auth_headers).json()
    assert detail["frames"][0]["image_url"] is not None
    assert detail["frames"][0]["image_url"].startswith("https://fake-s3.local/")
    assert detail["frames"][0]["purged"] is False


def test_video_media_not_found(auth_headers) -> None:
    assert client.get(f"/videos/{uuid.uuid4()}/media", headers=auth_headers).status_code == 404


def test_video_not_found(auth_headers) -> None:
    resp = client.get(f"/videos/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404
