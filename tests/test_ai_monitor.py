"""AI Review observability: runs list, drill-down, stats, re-run."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from evas import worker
from evas.api.app import app
from evas.checklists import EXAMPLE_CHECKLIST_ITEMS, EXAMPLE_CHECKLIST_NAME
from evas.db import session_scope
from evas.enums import JobType, UserRole
from evas.jobs import enqueue
from evas.models import AiRun, Checklist, Client, ProcessingJob, Video

client = TestClient(app)


def _ingest(fake_s3, sample_video_bytes) -> uuid.UUID:
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
    uri = "s3://evas-videos/acme/mon.mp4"
    fake_s3.put(uri, sample_video_bytes)
    with session_scope() as s:
        enqueue(
            s, job_type=JobType.ingest, payload={"client_id": str(client_id), "source_uri": uri}
        )
    while worker.run_once():
        pass
    with session_scope() as s:
        return s.scalars(select(Video.id)).one()


def test_runs_list(auth_headers, fake_s3, fake_ai, sample_video_bytes) -> None:
    _ingest(fake_s3, sample_video_bytes)
    rows = client.get("/ai/runs", headers=auth_headers).json()
    assert len(rows) == 1
    run = rows[0]
    assert run["status"] == "completed"
    assert run["frames_done"] == run["frames_total"] > 0
    assert run["grade"] is not None
    assert run["cost_usd"] >= 0
    assert run["flagged_frames"] >= 1  # fake reviewer makes holding_broom low-confidence


def test_runs_carry_checklist_provenance(
    auth_headers, fake_s3, fake_ai, sample_video_bytes
) -> None:
    _ingest(fake_s3, sample_video_bytes)
    run = client.get("/ai/runs", headers=auth_headers).json()[0]
    assert run["checklist_name"] == EXAMPLE_CHECKLIST_NAME
    assert run["checklist_version"] == 1
    assert run["prompt_is_custom"] is False  # seeded checklist has no prompt_template

    run_id = run["id"]
    detail = client.get(f"/ai/runs/{run_id}", headers=auth_headers).json()
    cl = detail["checklist"]
    assert cl["name"] == EXAMPLE_CHECKLIST_NAME and cl["version"] == 1
    assert len(cl["items"]) == len(EXAMPLE_CHECKLIST_ITEMS)  # item defs for type-aware rendering


def test_rerun_with_checklist_override(auth_headers, fake_s3, fake_ai, sample_video_bytes) -> None:
    video_id = _ingest(fake_s3, sample_video_bytes)
    run_id = client.get("/ai/runs", headers=auth_headers).json()[0]["id"]
    with session_scope() as s:
        checklist_id = s.scalars(select(Checklist.id)).first()

    ok = client.post(
        f"/ai/runs/{run_id}/rerun",
        json={"checklist_id": str(checklist_id)},
        headers=auth_headers,
    )
    assert ok.status_code == 202, ok.text
    with session_scope() as s:
        job = s.scalars(
            select(ProcessingJob)
            .where(ProcessingJob.job_type == JobType.ai_review, ProcessingJob.video_id == video_id)
            .order_by(ProcessingJob.queued_at.desc())
        ).first()
        assert job is not None and job.payload.get("checklist_id") == str(checklist_id)

    bogus = client.post(
        f"/ai/runs/{run_id}/rerun",
        json={"checklist_id": str(uuid.uuid4())},
        headers=auth_headers,
    )
    assert bogus.status_code == 404


def test_run_detail_has_triage(auth_headers, fake_s3, fake_ai, sample_video_bytes) -> None:
    _ingest(fake_s3, sample_video_bytes)
    run_id = client.get("/ai/runs", headers=auth_headers).json()[0]["id"]
    triage = client.get(f"/ai/runs/{run_id}", headers=auth_headers).json()["triage"]
    assert "counts" in triage and triage["count"] >= 1
    assert triage["counts"]["low_confidence"] >= 1  # fake reviewer makes holding_broom low-conf


def test_send_to_human(auth_headers, make_user, fake_s3, fake_ai, sample_video_bytes) -> None:
    video_id = _ingest(fake_s3, sample_video_bytes)
    run_id = client.get("/ai/runs", headers=auth_headers).json()[0]["id"]
    reviewer_id, _ = make_user(role=UserRole.reviewer)

    res = client.post(
        f"/ai/runs/{run_id}/send-to-human",
        json={"reviewer_id": str(reviewer_id)},
        headers=auth_headers,
    )
    assert res.status_code == 201, res.text
    revs = client.get(f"/videos/{video_id}/human-reviews", headers=auth_headers).json()
    assert any(r["reviewer_id"] == str(reviewer_id) for r in revs)

    bogus = client.post(
        f"/ai/runs/{run_id}/send-to-human",
        json={"reviewer_id": str(uuid.uuid4())},
        headers=auth_headers,
    )
    assert bogus.status_code == 404


def test_runs_filters(auth_headers, fake_s3, fake_ai, sample_video_bytes) -> None:
    _ingest(fake_s3, sample_video_bytes)
    assert len(client.get("/ai/runs?has_issues=true", headers=auth_headers).json()) == 1
    assert client.get("/ai/runs?status=failed", headers=auth_headers).json() == []
    assert client.get("/ai/runs?prompt_version=9.9.9", headers=auth_headers).json() == []


def test_run_drilldown(auth_headers, fake_s3, fake_ai, sample_video_bytes) -> None:
    _ingest(fake_s3, sample_video_bytes)
    run_id = client.get("/ai/runs", headers=auth_headers).json()[0]["id"]
    body = client.get(f"/ai/runs/{run_id}", headers=auth_headers).json()
    assert body["frames"]
    first = body["frames"][0]
    assert "findings" in first and "confidence" in first
    assert first["image_url"] is not None  # presigned, browser-fetchable frame image
    assert body["cost"]["cost_per_frame"] is not None
    assert body["issues"]["flagged_count"] >= 1
    assert "grade" in body["human"]  # no human review yet → null, key present


def test_run_drilldown_404(auth_headers) -> None:
    assert client.get(f"/ai/runs/{uuid.uuid4()}", headers=auth_headers).status_code == 404


def test_stats(auth_headers, fake_s3, fake_ai, sample_video_bytes) -> None:
    _ingest(fake_s3, sample_video_bytes)
    body = client.get("/ai/stats", headers=auth_headers).json()
    assert body["overall"]["completed"] == 1
    assert body["overall"]["error_rate"] == 0.0
    assert body["overall"]["avg_confidence"] is not None
    assert body["overall"]["flagged_rate"] > 0
    assert len(body["by_model"]) == 1
    assert len(body["by_prompt_version"]) == 1


def test_rerun_creates_new_job(auth_headers, fake_s3, fake_ai, sample_video_bytes) -> None:
    video_id = _ingest(fake_s3, sample_video_bytes)
    run_id = client.get("/ai/runs", headers=auth_headers).json()[0]["id"]
    resp = client.post(f"/ai/runs/{run_id}/rerun", headers=auth_headers)
    assert resp.status_code == 202
    with session_scope() as s:
        pending = s.scalars(
            select(ProcessingJob).where(
                ProcessingJob.job_type == JobType.ai_review,
                ProcessingJob.video_id == video_id,
            )
        ).all()
        # original run's job is done; the re-run adds a fresh queued one.
        assert any(j.id == uuid.UUID(resp.json()["job_id"]) for j in pending)

    while worker.run_once():
        pass
    # Re-run preserved history: two runs now exist for the video.
    with session_scope() as s:
        runs = s.scalars(select(AiRun).where(AiRun.video_id == video_id)).all()
        assert len(runs) == 2


def test_soft_deleted_video_excluded(auth_headers, fake_s3, fake_ai, sample_video_bytes) -> None:
    """Runs for a soft-deleted video must not leak into observability."""
    import datetime

    video_id = _ingest(fake_s3, sample_video_bytes)
    assert len(client.get("/ai/runs", headers=auth_headers).json()) == 1
    assert client.get("/ai/stats", headers=auth_headers).json()["overall"]["completed"] == 1

    with session_scope() as s:
        v = s.get(Video, video_id)
        assert v is not None
        v.deleted_at = datetime.datetime.now(datetime.UTC)

    assert client.get("/ai/runs", headers=auth_headers).json() == []
    stats = client.get("/ai/stats", headers=auth_headers).json()
    assert stats["overall"]["completed"] == 0
    assert stats["by_model"] == []
    assert stats["by_prompt_version"] == []


def test_requires_admin(make_user, fake_s3, fake_ai, sample_video_bytes) -> None:
    _ingest(fake_s3, sample_video_bytes)
    _, token = make_user(role=UserRole.reviewer)
    assert client.get("/ai/runs", headers={"Authorization": f"Bearer {token}"}).status_code == 403
