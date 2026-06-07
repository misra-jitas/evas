"""Webhook endpoint management (admin only)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from evas.api.schemas import WebhookCreate, WebhookOut
from evas.audit import write_audit
from evas.auth import require_roles
from evas.db import get_session
from evas.enums import UserRole
from evas.models import Client, User, WebhookEndpoint
from evas.webhooks import EVENT_AI_REVIEWED, EVENT_HUMAN_REVIEWED

router = APIRouter(tags=["webhooks"])
_admin = require_roles(UserRole.admin)

_DEFAULT_EVENTS = [EVENT_AI_REVIEWED, EVENT_HUMAN_REVIEWED]


def _to_out(ep: WebhookEndpoint) -> WebhookOut:
    return WebhookOut(
        id=ep.id,
        client_id=ep.client_id,
        url=ep.url,
        events=list(ep.events),
        is_active=ep.is_active,
        created_at=ep.created_at,
    )


@router.post("/clients/{client_id}/webhooks", response_model=WebhookOut, status_code=201)
def create_webhook(
    client_id: uuid.UUID,
    req: WebhookCreate,
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
) -> WebhookOut:
    client = session.get(Client, client_id)
    if client is None or client.deleted_at is not None:
        raise HTTPException(status_code=404, detail="client not found")
    ep = WebhookEndpoint(
        client_id=client_id,
        url=req.url,
        secret=req.secret,
        events=req.events or list(_DEFAULT_EVENTS),
    )
    session.add(ep)
    session.flush()
    write_audit(
        session,
        entity_type="webhook_endpoint",
        entity_id=ep.id,
        action="created",
        new_value={"url": ep.url, "events": list(ep.events)},
        user_id=user.id,
    )
    return _to_out(ep)


@router.get("/clients/{client_id}/webhooks", response_model=list[WebhookOut])
def list_webhooks(
    client_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
) -> list[WebhookOut]:
    rows = session.scalars(
        select(WebhookEndpoint).where(WebhookEndpoint.client_id == client_id)
    ).all()
    return [_to_out(ep) for ep in rows]


@router.delete("/webhooks/{webhook_id}", status_code=200)
def deactivate_webhook(
    webhook_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
) -> dict[str, str]:
    ep = session.get(WebhookEndpoint, webhook_id)
    if ep is None:
        raise HTTPException(status_code=404, detail="webhook not found")
    ep.is_active = False
    write_audit(
        session,
        entity_type="webhook_endpoint",
        entity_id=ep.id,
        action="deactivated",
        user_id=user.id,
    )
    return {"status": "deactivated"}
