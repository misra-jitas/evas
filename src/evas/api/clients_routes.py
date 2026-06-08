"""Client management (admin): add / rename / edit / delete clients.

Soft-delete via deleted_at; slug is unique among live clients. Every mutation
writes an audit_log row (non-negotiable rule).
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from evas.api.schemas import ClientCreate, ClientOut, ClientUpdate
from evas.audit import write_audit
from evas.auth import require_roles
from evas.db import get_session
from evas.enums import UserRole
from evas.models import Client, User, Video

router = APIRouter(prefix="/clients", tags=["clients"])
_admin = require_roles(UserRole.admin)

_DEFAULT_SAMPLING: dict[str, Any] = {"interval_seconds": 5, "max_frames": 300, "frame_width": 1280}


def _video_count(session: Session, client_id: uuid.UUID) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(Video)
            .where(Video.client_id == client_id, Video.deleted_at.is_(None))
        )
        or 0
    )


def _to_out(session: Session, c: Client) -> ClientOut:
    return ClientOut(
        id=c.id,
        name=c.name,
        slug=c.slug,
        sampling_config=c.sampling_config,
        frame_retention_days=c.frame_retention_days,
        video_archive_days=c.video_archive_days,
        created_at=c.created_at,
        video_count=_video_count(session, c.id),
    )


def _get_active(session: Session, client_id: uuid.UUID) -> Client:
    c = session.get(Client, client_id)
    if c is None or c.deleted_at is not None:
        raise HTTPException(status_code=404, detail="client not found")
    return c


def _slug_taken(session: Session, slug: str, exclude: uuid.UUID | None = None) -> bool:
    # The schema enforces a hard UNIQUE on slug (no partial index), so a slug
    # stays reserved even after a soft delete — check all rows, not just live.
    stmt = select(Client.id).where(Client.slug == slug)
    if exclude is not None:
        stmt = stmt.where(Client.id != exclude)
    return session.scalars(stmt).first() is not None


@router.get("", response_model=list[ClientOut])
def list_clients(
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
) -> list[ClientOut]:
    rows = session.scalars(
        select(Client).where(Client.deleted_at.is_(None)).order_by(Client.created_at.desc())
    ).all()
    return [_to_out(session, c) for c in rows]


@router.post("", response_model=ClientOut, status_code=201)
def create_client(
    req: ClientCreate,
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
) -> ClientOut:
    if _slug_taken(session, req.slug):
        raise HTTPException(status_code=409, detail=f"slug {req.slug!r} already in use")
    c = Client(
        name=req.name,
        slug=req.slug,
        sampling_config=req.sampling_config or dict(_DEFAULT_SAMPLING),
        frame_retention_days=req.frame_retention_days,
        video_archive_days=req.video_archive_days,
    )
    session.add(c)
    session.flush()
    write_audit(
        session,
        entity_type="client",
        entity_id=c.id,
        action="created",
        new_value={"name": c.name, "slug": c.slug},
        user_id=user.id,
    )
    return _to_out(session, c)


@router.get("/{client_id}", response_model=ClientOut)
def get_client(
    client_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
) -> ClientOut:
    return _to_out(session, _get_active(session, client_id))


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: uuid.UUID,
    req: ClientUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
) -> ClientOut:
    c = _get_active(session, client_id)
    if req.slug is not None and req.slug != c.slug and _slug_taken(session, req.slug, exclude=c.id):
        raise HTTPException(status_code=409, detail=f"slug {req.slug!r} already in use")
    if req.name is not None:
        c.name = req.name
    if req.slug is not None:
        c.slug = req.slug
    if req.sampling_config is not None:
        c.sampling_config = req.sampling_config
    if req.frame_retention_days is not None:
        c.frame_retention_days = req.frame_retention_days
    if req.video_archive_days is not None:
        c.video_archive_days = req.video_archive_days
    write_audit(
        session,
        entity_type="client",
        entity_id=c.id,
        action="updated",
        new_value=req.model_dump(exclude_none=True),
        user_id=user.id,
    )
    session.flush()
    return _to_out(session, c)


@router.delete("/{client_id}", status_code=204)
def delete_client(
    client_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
) -> None:
    c = _get_active(session, client_id)
    c.deleted_at = datetime.datetime.now(datetime.UTC)
    write_audit(
        session,
        entity_type="client",
        entity_id=c.id,
        action="deleted",
        user_id=user.id,
    )
