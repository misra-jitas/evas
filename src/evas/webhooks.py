"""Webhook delivery: the `notify` job fans an event out to a client's active
endpoints, signing each POST with the endpoint secret (HMAC-SHA256).

Deliveries are recorded in webhook_deliveries and are idempotent on retry:
already-delivered (2xx) rows are skipped; any non-2xx raises so the job's
normal retry/dead-letter logic applies.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from evas.config import get_settings
from evas.enums import JobType
from evas.jobs import enqueue
from evas.models import ProcessingJob, Video, WebhookDelivery, WebhookEndpoint

EVENT_AI_REVIEWED = "video.ai_reviewed"
EVENT_HUMAN_REVIEWED = "video.human_reviewed"


def sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def enqueue_notify(session: Session, video_id: uuid.UUID, event: str) -> ProcessingJob:
    """Queue a notify job for an event. Does not commit."""
    return enqueue(
        session,
        job_type=JobType.notify,
        video_id=video_id,
        payload={"video_id": str(video_id), "event": event},
    )


def _existing_delivery(
    session: Session, endpoint_id: uuid.UUID, event: str, video_id: str
) -> WebhookDelivery | None:
    rows = session.scalars(
        select(WebhookDelivery).where(
            WebhookDelivery.endpoint_id == endpoint_id, WebhookDelivery.event == event
        )
    ).all()
    for row in rows:
        if str(row.payload.get("video_id")) == video_id:
            return row
    return None


def handle_notify(session: Session, job: ProcessingJob) -> None:
    payload = job.payload
    event = str(payload["event"])
    video_id = str(payload["video_id"])
    video = session.get(Video, uuid.UUID(video_id))
    if video is None:
        raise ValueError(f"video {video_id} not found")

    endpoints = session.scalars(
        select(WebhookEndpoint).where(
            WebhookEndpoint.client_id == video.client_id,
            WebhookEndpoint.is_active.is_(True),
            WebhookEndpoint.events.contains([event]),
        )
    ).all()

    body_obj = {"event": event, "video_id": video_id, "client_id": str(video.client_id)}
    body = json.dumps(body_obj, sort_keys=True).encode("utf-8")
    settings = get_settings()
    failures: list[str] = []

    for endpoint in endpoints:
        delivery = _existing_delivery(session, endpoint.id, event, video_id)
        if delivery is not None and delivery.delivered_at is not None:
            continue  # already delivered; idempotent skip
        if delivery is None:
            delivery = WebhookDelivery(
                endpoint_id=endpoint.id, event=event, payload=body_obj, attempts=0
            )
            session.add(delivery)
        delivery.attempts += 1
        headers = {
            "Content-Type": "application/json",
            "X-EVAS-Event": event,
            "X-EVAS-Signature": sign(endpoint.secret, body),
        }
        try:
            resp = httpx.post(
                endpoint.url,
                content=body,
                headers=headers,
                timeout=settings.webhook_timeout_seconds,
            )
            delivery.status_code = resp.status_code
            if 200 <= resp.status_code < 300:
                delivery.delivered_at = _utcnow()
            else:
                failures.append(f"{endpoint.url} -> HTTP {resp.status_code}")
        except httpx.HTTPError as exc:
            delivery.status_code = None
            failures.append(f"{endpoint.url} -> {exc!r}")

    if failures:
        # Persist delivery outcomes (including the successes) before raising, so
        # the worker's rollback-on-error doesn't undo them — keeps retries
        # idempotent (already-delivered endpoints are skipped next time).
        session.commit()
        raise RuntimeError("; ".join(failures))


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)
