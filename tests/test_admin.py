"""Ops metrics endpoint: dead jobs, webhook failures, cost spikes."""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

from evas.api.app import app
from evas.db import session_scope
from evas.enums import JobStatus, JobType, RunStatus, UserRole
from evas.models import (
    AiRun,
    Checklist,
    Client,
    ProcessingJob,
    Video,
    WebhookDelivery,
    WebhookEndpoint,
)

client = TestClient(app)


def _seed_ops_state() -> None:
    with session_scope() as s:
        c = Client(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}", sampling_config={})
        s.add(c)
        s.flush()
        checklist = Checklist(client_id=c.id, name="cl", version=1, items=[], is_active=True)
        s.add(checklist)
        video = Video(client_id=c.id, source_uri="s3://b/v.mp4", file_hash=uuid.uuid4().hex)
        s.add(video)
        s.flush()
        # Dead job.
        s.add(
            ProcessingJob(
                video_id=video.id, job_type=JobType.ai_review, status=JobStatus.dead, attempts=3
            )
        )
        # Webhook failure (attempted, not delivered).
        ep = WebhookEndpoint(
            client_id=c.id, url="https://x", secret="s", events=["video.ai_reviewed"]
        )
        s.add(ep)
        s.flush()
        s.add(
            WebhookDelivery(
                endpoint_id=ep.id,
                event="video.ai_reviewed",
                payload={},
                attempts=2,
                status_code=500,
            )
        )
        # Cost today, none yesterday -> spike with no baseline.
        s.add(
            AiRun(
                video_id=video.id,
                checklist_id=checklist.id,
                model="m",
                prompt_version="1.0.0",
                status=RunStatus.completed,
                cost_usd=Decimal("0.50"),
                completed_at=datetime.datetime.now(datetime.UTC),
            )
        )


def test_metrics(auth_headers) -> None:
    _seed_ops_state()
    resp = client.get("/admin/metrics", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["dead_jobs"] >= 1
    assert body["webhook_failures"] >= 1
    assert len(body["cost_spikes"]) >= 1


def test_metrics_requires_admin(make_user) -> None:
    _, token = make_user(role=UserRole.reviewer)
    resp = client.get("/admin/metrics", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
