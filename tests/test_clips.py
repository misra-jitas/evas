"""Clips: manual + auto segmentation and clip review -> ai_clip_findings."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from evas import worker
from evas.api.app import app
from evas.checklists import EXAMPLE_CHECKLIST_ITEMS, EXAMPLE_CHECKLIST_NAME
from evas.db import session_scope
from evas.models import AiClipFinding, Checklist, Client, Video

client = TestClient(app)


def _ingest_reviewed_video(fake_s3, sample_video_bytes) -> uuid.UUID:
    with session_scope() as s:
        c = Client(
            name="Acme",
            slug=f"acme-{uuid.uuid4().hex[:6]}",
            sampling_config={"interval_seconds": 1, "max_frames": 5, "frame_width": 160},
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
    source_uri = "s3://evas-videos/acme/clip.mp4"
    fake_s3.put(source_uri, sample_video_bytes)
    from evas.enums import JobType
    from evas.jobs import enqueue

    with session_scope() as s:
        enqueue(
            s,
            job_type=JobType.ingest,
            payload={"client_id": str(client_id), "source_uri": source_uri},
        )
    while worker.run_once():
        pass
    with session_scope() as s:
        return s.scalars(select(Video.id)).one()


def test_manual_and_auto_segmentation(auth_headers, fake_s3, fake_ai, sample_video_bytes) -> None:
    video_id = _ingest_reviewed_video(fake_s3, sample_video_bytes)

    manual = client.post(
        f"/videos/{video_id}/clips",
        json={"start_seconds": 0.0, "end_seconds": 1.0, "label": "intro"},
        headers=auth_headers,
    )
    assert manual.status_code == 201
    assert manual.json()["label"] == "intro"

    auto = client.post(f"/videos/{video_id}/clips/auto", headers=auth_headers)
    assert auto.status_code == 201
    assert len(auto.json()) >= 1
    assert all(c["label"] == "auto" for c in auto.json())


def test_clip_review_produces_findings(auth_headers, fake_s3, fake_ai, sample_video_bytes) -> None:
    video_id = _ingest_reviewed_video(fake_s3, sample_video_bytes)
    client.post(f"/videos/{video_id}/clips/auto", headers=auth_headers)

    resp = client.post(f"/videos/{video_id}/clip-review", headers=auth_headers)
    assert resp.status_code == 202
    while worker.run_once():
        pass

    with session_scope() as s:
        n = s.scalar(select(func.count()).select_from(AiClipFinding))
        assert n and n >= 1

    listed = client.get(f"/videos/{video_id}/clips", headers=auth_headers)
    assert listed.status_code == 200
    # clip-scoped item is_sweeping should be present in findings
    assert any(c.get("findings") and "is_sweeping" in c["findings"] for c in listed.json())
