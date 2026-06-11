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


def test_scan_links_already_ingested_videos(auth_headers, fake_s3) -> None:
    # A video already exists (e.g. ingested via demo/CSV) with no source link.
    client_id = _seed_client()
    uri = "s3://evas-videos/acme/pre-existing.mp4"
    fake_s3.put(uri, b"fake-mp4-bytes")
    with session_scope() as s:
        v = Video(client_id=client_id, source_uri=uri, file_hash=uuid.uuid4().hex)
        s.add(v)
        s.flush()
        video_id = v.id

    src = _register(client_id, auth_headers)  # prefix s3://evas-videos/acme/
    while worker.run_once():
        pass

    detail = client.get(f"/sources/{src['id']}", headers=auth_headers).json()
    assert detail["last_sync_result"]["linked"] == 1
    assert detail["last_sync_result"]["registered"] == 0  # not re-ingested
    with session_scope() as s:
        assert s.get(Video, video_id).source_id == uuid.UUID(src["id"])
    assert detail["funnel"]["total"] == 1  # now visible under the source


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


def test_scan_list_failure_marks_source_error(auth_headers, fake_s3, monkeypatch) -> None:
    """A bucket-listing failure must move the source to 'error', not sit on 'syncing'."""
    client_id = _seed_client()
    src = _register(client_id, auth_headers, uri_prefix="s3://nonexistent-bucket/")
    source_id = src["id"]

    def boom(*_args, **_kw):
        raise RuntimeError("NoSuchBucket: The specified bucket does not exist")

    monkeypatch.setattr("evas.pipeline.sync.list_objects", boom)
    while worker.run_once():
        pass

    detail = client.get(f"/sources/{source_id}", headers=auth_headers).json()
    assert detail["status"] == "error"  # not stuck on "syncing"
    assert "NoSuchBucket" in detail["last_error"]
    assert detail["last_sync_result"]["error"] == "list_failed"


def test_duplicate_prefix_returns_409(auth_headers, fake_s3) -> None:
    client_id = _seed_client()
    _register(client_id, auth_headers, uri_prefix="s3://evas-videos/dup/")
    resp = client.post(
        "/sources",
        json={
            "client_id": str(client_id),
            "label": "again",
            "type": "s3",
            "uri_prefix": "s3://evas-videos/dup/",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


def test_readd_revives_soft_deleted_source(auth_headers, fake_s3) -> None:
    """Deleting then re-registering the same prefix revives the row, not a 500."""
    client_id = _seed_client()
    first = _register(client_id, auth_headers, uri_prefix="s3://evas-videos/revive/")
    assert client.delete(f"/sources/{first['id']}", headers=auth_headers).status_code == 204
    again = _register(client_id, auth_headers, uri_prefix="s3://evas-videos/revive/", label="back")
    assert again["id"] == first["id"]  # same row, revived
    assert again["label"] == "back"


def test_list_credentials(auth_headers, monkeypatch) -> None:
    assert client.get("/sources/credentials", headers=auth_headers).json() == {"refs": []}
    monkeypatch.setenv("EVAS_CRED_ACME_PROD_ACCESS_KEY_ID", "x")
    monkeypatch.setenv("EVAS_CRED_ACME_PROD_SECRET_ACCESS_KEY", "y")
    assert client.get("/sources/credentials", headers=auth_headers).json() == {
        "refs": ["ACME_PROD"]
    }


def test_credential_resolution_from_env(monkeypatch) -> None:
    """A named credential_ref resolves per-source keys from namespaced env vars."""
    from evas import storage

    storage.get_s3_client.cache_clear()
    # Unknown ref with no env → a clear, actionable error (surfaced as source error).
    try:
        storage.get_s3_client("acme-prod")
        raise AssertionError("expected ValueError for missing credentials")
    except ValueError as exc:
        assert "EVAS_CRED_ACME_PROD_ACCESS_KEY_ID" in str(exc)

    # With env set, the client builds (slug = uppercased, non-alnum -> "_").
    monkeypatch.setenv("EVAS_CRED_ACME_PROD_ACCESS_KEY_ID", "AKIA_TEST")
    monkeypatch.setenv("EVAS_CRED_ACME_PROD_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("EVAS_CRED_ACME_PROD_REGION", "eu-west-1")
    storage.get_s3_client.cache_clear()
    client = storage.get_s3_client("acme-prod")
    assert client.meta.region_name == "eu-west-1"
    storage.get_s3_client.cache_clear()


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
