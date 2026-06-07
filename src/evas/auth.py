"""Stateless JWT auth. No credentials are stored (the users table has no
password column and the schema is locked) — tokens are signed with
EVAS_JWT_SECRET and carry the user id, role, and client_id.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Callable, Iterable
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from evas.config import get_settings
from evas.db import get_session
from evas.enums import UserRole
from evas.models import User

_bearer = HTTPBearer(auto_error=True)


def create_access_token(user: User) -> str:
    settings = get_settings()
    now = datetime.datetime.now(datetime.UTC)
    claims = {
        "sub": str(user.id),
        "role": user.role.value,
        "client_id": str(user.client_id) if user.client_id else None,
        "iat": int(now.timestamp()),
        "exp": int((now + datetime.timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        claims: dict[str, Any] = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        return claims
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token"
        ) from exc


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    session: Session = Depends(get_session),
) -> User:
    claims = decode_token(creds.credentials)
    try:
        user_id = uuid.UUID(str(claims.get("sub")))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="invalid token subject") from exc
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="user not found or inactive")
    return user


def require_roles(*roles: UserRole) -> Callable[..., User]:
    """Dependency factory: allow only the given roles."""
    allowed = set(roles)

    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="insufficient role")
        return user

    return _dep


def tenancy_client_id(user: User) -> uuid.UUID | None:
    """client_id a request must be scoped to, or None for internal staff."""
    if user.role == UserRole.client_viewer:
        return user.client_id
    return None


def assert_can_access_client(user: User, client_id: uuid.UUID) -> None:
    """404 (not 403) on cross-tenant access to avoid leaking existence."""
    scope = tenancy_client_id(user)
    if scope is not None and scope != client_id:
        raise HTTPException(status_code=404, detail="not found")


# Convenience role groups.
def staff() -> Iterable[UserRole]:
    return (UserRole.admin, UserRole.reviewer)
