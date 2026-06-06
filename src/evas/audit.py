"""Audit logging. Every status change must write an audit_log row.

user_id NULL means the action was performed by the system (workers, CLI).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from evas.models import AuditLog


def write_audit(
    session: Session,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    user_id: uuid.UUID | None = None,
) -> AuditLog:
    """Append an audit_log row. Does not commit (caller owns the transaction)."""
    row = AuditLog(
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_value=old_value,
        new_value=new_value,
    )
    session.add(row)
    return row


def record_status_change(
    session: Session,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    old_status: str | None,
    new_status: str,
    user_id: uuid.UUID | None = None,
) -> AuditLog:
    """Convenience wrapper for the common 'status_changed' audit event."""
    return write_audit(
        session,
        entity_type=entity_type,
        entity_id=entity_id,
        action="status_changed",
        old_value={"status": old_status} if old_status is not None else None,
        new_value={"status": new_status},
        user_id=user_id,
    )
