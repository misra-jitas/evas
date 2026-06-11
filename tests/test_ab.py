"""Prompt A/B: two prompt versions produce separate runs + a comparison report."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from evas import worker
from evas.api.app import app
from evas.checklists import EXAMPLE_CHECKLIST_ITEMS, EXAMPLE_CHECKLIST_NAME
from evas.db import session_scope
from evas.enums import JobType
from evas.jobs import enqueue
from evas.models import AiRun, Checklist, Client, Video

client = TestClient(app)


def _ingest_video(fake_s3, sample_video_bytes) -> uuid.UUID:
    with session_scope() as s:
        c = Client(
            name="Acme",
            slug=f"acme-{uuid.uuid4().hex[:6]}",
            sampling_config={"interval_seconds": 1, "max_frames": 3, "frame_width": 160},
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
        client_id = c.id
    uri = "s3://evas-videos/acme/ab.mp4"
    fake_s3.put(uri, sample_video_bytes)
    with session_scope() as s:
        enqueue(
            s, job_type=JobType.ingest, payload={"client_id": str(client_id), "source_uri": uri}
        )
    while worker.run_once():
        pass
    with session_scope() as s:
        return s.scalars(select(Video.id)).one()


def test_ab_runs_and_compare(auth_headers, fake_s3, fake_ai, sample_video_bytes) -> None:
    video_id = _ingest_video(fake_s3, sample_video_bytes)

    start = client.post(
        "/ab-tests",
        json={
            "video_ids": [str(video_id)],
            "prompt_version_a": "1.0.0",
            "prompt_version_b": "1.1.0",
        },
        headers=auth_headers,
    )
    assert start.status_code == 202
    assert start.json()["jobs_enqueued"] == 2
    while worker.run_once():
        pass

    # Both prompt versions now have completed runs.
    with session_scope() as s:
        versions = set(
            s.scalars(select(AiRun.prompt_version).where(AiRun.video_id == video_id)).all()
        )
        assert {"1.0.0", "1.1.0"} <= versions

    report = client.post(
        "/ab-tests/compare",
        json={
            "video_ids": [str(video_id)],
            "prompt_version_a": "1.0.0",
            "prompt_version_b": "1.1.0",
        },
        headers=auth_headers,
    )
    assert report.status_code == 200
    body = report.json()
    assert body["prompt_version_a"] == "1.0.0"
    assert len(body["videos"]) == 1
    assert body["videos"][0]["complete"] is True
    assert body["recommendation"]["promote"] in {"1.0.0", "1.1.0"}
    assert "item_disagreements" in body


def test_ab_requires_admin(make_user, fake_s3, fake_ai, sample_video_bytes) -> None:
    from evas.enums import UserRole

    video_id = _ingest_video(fake_s3, sample_video_bytes)
    _, token = make_user(role=UserRole.reviewer)
    resp = client.post(
        "/ab-tests",
        json={
            "video_ids": [str(video_id)],
            "prompt_version_a": "1.0.0",
            "prompt_version_b": "1.1.0",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
