"""Webhook delivery: signing, recording, idempotency, and failure retry."""

from __future__ import annotations

import uuid

import httpx
from sqlalchemy import select

from evas import worker
from evas.db import session_scope
from evas.enums import JobStatus
from evas.jobs import enqueue
from evas.models import Client, ProcessingJob, Video, WebhookDelivery, WebhookEndpoint
from evas.webhooks import EVENT_AI_REVIEWED, JobType, enqueue_notify, sign


class _Resp:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def _seed_endpoint(
    secret: str = "whsec", url: str = "https://hook.example/x"
) -> tuple[uuid.UUID, uuid.UUID]:
    with session_scope() as s:
        c = Client(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}", sampling_config={})
        s.add(c)
        s.flush()
        s.add(WebhookEndpoint(client_id=c.id, url=url, secret=secret, events=[EVENT_AI_REVIEWED]))
        v = Video(client_id=c.id, source_uri="s3://b/v.mp4", file_hash=uuid.uuid4().hex)
        s.add(v)
        s.flush()
        return c.id, v.id


def test_delivery_signed_and_recorded(monkeypatch) -> None:
    _, video_id = _seed_endpoint(secret="whsec")
    calls: list[dict] = []

    def fake_post(url, content, headers, timeout):
        calls.append({"url": url, "content": content, "headers": headers})
        return _Resp(200)

    monkeypatch.setattr(httpx, "post", fake_post)

    with session_scope() as s:
        enqueue_notify(s, video_id, EVENT_AI_REVIEWED)
    assert worker.run_once() is True

    assert len(calls) == 1
    sig = calls[0]["headers"]["X-EVAS-Signature"]
    assert sig == sign("whsec", calls[0]["content"])

    with session_scope() as s:
        d = s.scalars(select(WebhookDelivery)).one()
        assert d.status_code == 200
        assert d.delivered_at is not None
        assert d.attempts == 1
        job = s.scalars(select(ProcessingJob).where(ProcessingJob.job_type == JobType.notify)).one()
        assert job.status == JobStatus.done


def test_delivery_idempotent_on_replay(monkeypatch) -> None:
    _, video_id = _seed_endpoint()
    calls: list[str] = []
    monkeypatch.setattr(httpx, "post", lambda url, **kw: calls.append(url) or _Resp(200))

    for _ in range(2):
        with session_scope() as s:
            enqueue_notify(s, video_id, EVENT_AI_REVIEWED)
        worker.run_once()

    assert len(calls) == 1  # second notify skips the already-delivered endpoint
    with session_scope() as s:
        assert s.scalar(select(WebhookDelivery).where(WebhookDelivery.delivered_at.isnot(None)))


def test_failed_delivery_dead_letters(monkeypatch) -> None:
    _, video_id = _seed_endpoint()
    monkeypatch.setattr(httpx, "post", lambda url, **kw: _Resp(500))

    with session_scope() as s:
        enqueue(
            s,
            job_type=JobType.notify,
            video_id=video_id,
            payload={"video_id": str(video_id), "event": EVENT_AI_REVIEWED},
            max_attempts=1,
        )
    assert worker.run_once() is True

    with session_scope() as s:
        job = s.scalars(select(ProcessingJob).where(ProcessingJob.job_type == JobType.notify)).one()
        assert job.status == JobStatus.dead
        d = s.scalars(select(WebhookDelivery)).one()
        assert d.status_code == 500
        assert d.delivered_at is None
