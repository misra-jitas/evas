"""Checklist (review config) management (admin).

A checklist is a client's review config: the list of items (what to ask, of any
supported type) plus an optional `prompt_template` (the UI-editable framing).
Versions are immutable — saving config creates a new version and makes it the
active one for that (client, name), deactivating the prior active version. Every
mutation writes an audit_log row (non-negotiable rule).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from evas.api.schemas import ChecklistOut, ChecklistSave
from evas.audit import write_audit
from evas.auth import require_roles
from evas.checklists import validate_items
from evas.db import get_session
from evas.enums import GradingMode, UserRole
from evas.models import Checklist, Client, User

router = APIRouter(prefix="/clients/{client_id}/checklists", tags=["checklists"])
_admin = require_roles(UserRole.admin)


def _to_out(c: Checklist) -> ChecklistOut:
    return ChecklistOut(
        id=c.id,
        client_id=c.client_id,
        name=c.name,
        version=c.version,
        grading_mode=c.grading_mode.value,
        items=c.items,
        prompt_template=c.prompt_template,
        is_active=c.is_active,
        created_at=c.created_at,
    )


def _require_client(session: Session, client_id: uuid.UUID) -> Client:
    c = session.get(Client, client_id)
    if c is None or c.deleted_at is not None:
        raise HTTPException(status_code=404, detail="client not found")
    return c


@router.get("", response_model=list[ChecklistOut])
def list_checklists(
    client_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
) -> list[ChecklistOut]:
    _require_client(session, client_id)
    rows = session.scalars(
        select(Checklist)
        .where(Checklist.client_id == client_id)
        .order_by(Checklist.name, Checklist.version.desc())
    ).all()
    return [_to_out(c) for c in rows]


@router.get("/active", response_model=ChecklistOut)
def get_active_checklist(
    client_id: uuid.UUID,
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
) -> ChecklistOut:
    _require_client(session, client_id)
    row = session.scalars(
        select(Checklist)
        .where(Checklist.client_id == client_id, Checklist.is_active.is_(True))
        .order_by(Checklist.version.desc())
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="no active checklist for this client")
    return _to_out(row)


@router.post("", response_model=ChecklistOut, status_code=201)
def save_checklist(
    client_id: uuid.UUID,
    req: ChecklistSave,
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
) -> ChecklistOut:
    """Save a new version of a (client, name) checklist and make it active."""
    _require_client(session, client_id)
    try:
        items = validate_items(req.items)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        grading_mode = GradingMode(req.grading_mode)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"bad grading_mode: {req.grading_mode!r}"
        ) from exc

    existing = session.scalars(
        select(Checklist)
        .where(Checklist.client_id == client_id, Checklist.name == req.name)
        .order_by(Checklist.version.desc())
    ).all()
    next_version = (existing[0].version + 1) if existing else 1
    for c in existing:
        c.is_active = False

    checklist = Checklist(
        client_id=client_id,
        name=req.name,
        version=next_version,
        grading_mode=grading_mode,
        items=items,
        prompt_template=req.prompt_template,
        is_active=True,
    )
    session.add(checklist)
    session.flush()
    write_audit(
        session,
        entity_type="checklist",
        entity_id=checklist.id,
        action="created",
        new_value={"name": req.name, "version": next_version, "items": len(items)},
        user_id=user.id,
    )
    return _to_out(checklist)
