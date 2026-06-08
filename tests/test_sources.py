"""Sources: registration, S3 scan → ingest, idempotent re-scan, URL stub, funnel."""

from __future__ import annotations

import subprocess
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from evas import worker
from evas.api.app import app
from evas.checklists import EXAMPLE_CHECKLIST_ITEMS, EXAMPLE_CHECKLIST_NAME
from evas.db import session_scope
from evas.enums import UserRole
from evas.models import Checklist, Client, Source, Video

client = TestClient(app)


def _make_video_bytes(tmp_path, duration: int) -> bytes:
    """A distinct, valid mp4 per duration (so file hashes differ → no dedup)."""
    out = tmp_path / f"v{duration}.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=duration={duration}:size=160x120:rate=10",
            "-pix_fmt",
            "yuv420p",
            str(out),
        ],
        check=True,
    )
    return out.read_bytes()


def _seed_client() -> uuid.UUID:
    with session_scope() as s:
        c = Client(
            name="Acme",
            slug=f"acme-{uuid.uuid4().hex[:6]}",
            sampling_config={"interval_seconds": 1, "max_frames": 2, "frame_width": 120},
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


def _register(client_id, headers, **over) -> dict:
    body = {
        "client_id": str(client_id),
        "label": "Halo shift uploads",
        "type": "s3",
        "uri_prefix": "s3://evas-videos/acme/",
    }
    body.update(over)
    resp = client.post("/sources", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_register_sets_syncing_and_enqueues(auth_headers, fake_s3) -> None:
    client_id = _seed_client()
    body = _register(client_id, auth_headers)
    assert body["status"] == "syncing"
    assert body["funnel"]["total"] == 0
    assert body["credential_ref"] is None


def test_scan_enumerates_and_ingests(auth_headers, fake_s3, fake_ai, tmp_path) -> None:
    client_id = _seed_client()
    fake_s3.put("s3://evas-videos/acme/a.mp4", _make_video_bytes(tmp_path, 1))
    fake_s3.put("s3://evas-videos/acme/b.mp4", _make_video_bytes(tmp_path, 2))
    fake_s3.put("s3://evas-videos/acme/notes.txt", b"not a video")  # filtered out

    src = _register(client_id, auth_headers)
    source_id = src["id"]
    while worker.run_once():
        pass

    detail = client.get(f"/sources/{source_id}", headers=auth_headers).json()
    assert detail["status"] == "connected"
    assert detail["last_sync_result"]["discovered"] == 2  # .txt excluded
    assert detail["last_sync_result"]["registered"] == 2
    assert detail["last_sync_result"]["failed"] == 0
    # Two distinct videos got tagged with the source.
    with session_scope() as s:
        vids = s.scalars(select(Video).where(Video.source_id == uuid.UUID(source_id))).all()
        assert len(vids) == 2
        assert all(v.source_id == uuid.UUID(source_id) for v in vids)
    # Funnel: both reached ai_reviewed (in_review bucket), none left to ingest.
    assert detail["funnel"]["total"] == 2
    assert detail["funnel"]["in_review"] == 2
    assert detail["funnel"]["to_ingest"] == 0

    # Videos list scoped to the source.
    listed = client.get(f"/videos?source_id={source_id}", headers=auth_headers).json()
    assert len(listed) == 2


def test_rescan_is_idempotent(auth_headers, fake_s3, fake_ai, tmp_path) -> None:
    client_id = _seed_client()
    fake_s3.put("s3://evas-videos/acme/a.mp4", _make_video_bytes(tmp_path, 1))
    src = _register(client_id, auth_headers)
    source_id = src["id"]
    while worker.run_once():
        pass

    again = client.post(f"/sources/{source_id}/sync", headers=auth_headers)
    assert again.status_code == 202
    while worker.run_once():
        pass

    detail = client.get(f"/sources/{source_id}", headers=auth_headers).json()
    assert detail["last_sync_result"]["discovered"] == 1
    assert detail["last_sync_result"]["registered"] == 0  # already known
    assert detail["last_sync_result"]["skipped"] == 1
    with session_scope() as s:
        assert (
            len(s.scalars(select(Video).where(Video.source_id == uuid.UUID(source_id))).all()) == 1
        )


def test_url_source_is_not_yet_supported(auth_headers, fake_s3) -> None:
    client_id = _seed_client()
    src = _register(client_id, auth_headers, type="url", uri_prefix="https://example.com/listing")
    source_id = src["id"]
    while worker.run_once():
        pass

    detail = client.get(f"/sources/{source_id}", headers=auth_headers).json()
    assert detail["status"] == "error"
    assert "not yet supported" in detail["last_error"]
    assert detail["last_sync_result"]["error"] == "unsupported_source_type"


def test_patch_disable_and_soft_delete(auth_headers, fake_s3) -> None:
    client_id = _seed_client()
    src = _register(client_id, auth_headers, scan_now=False)
    source_id = src["id"]
    assert src["status"] == "connected"

    patched = client.patch(
        f"/sources/{source_id}", json={"enabled": False, "label": "renamed"}, headers=auth_headers
    ).json()
    assert patched["status"] == "disabled"
    assert patched["label"] == "renamed"

    # Disabled sources refuse a sync.
    assert client.post(f"/sources/{source_id}/sync", headers=auth_headers).status_code == 409

    assert client.delete(f"/sources/{source_id}", headers=auth_headers).status_code == 204
    assert client.get(f"/sources/{source_id}", headers=auth_headers).status_code == 404
    with session_scope() as s:
        assert s.get(Source, uuid.UUID(source_id)).deleted_at is not None


def test_requires_admin(make_user, fake_s3) -> None:
    client_id = _seed_client()
    _, token = make_user(role=UserRole.reviewer)
    resp = client.post(
        "/sources",
        json={
            "client_id": str(client_id),
            "label": "x",
            "type": "s3",
            "uri_prefix": "s3://evas-videos/acme/",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
