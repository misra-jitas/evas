"""Auth endpoints. Token minting is an interim bootstrap mechanism gated by
EVAS_BOOTSTRAP_TOKEN — real credential verification belongs to an external IdP
(see Evas2.md). No passwords are stored.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from evas.api.schemas import TokenRequest, TokenResponse
from evas.auth import create_access_token
from evas.config import get_settings
from evas.db import get_session
from evas.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
def issue_token(
    req: TokenRequest,
    x_bootstrap_token: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> TokenResponse:
    settings = get_settings()
    if not settings.bootstrap_token:
        raise HTTPException(status_code=503, detail="token issuance is not configured")
    if x_bootstrap_token != settings.bootstrap_token:
        raise HTTPException(status_code=401, detail="invalid bootstrap token")
    user = session.scalars(select(User).where(User.email == req.email)).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="unknown or inactive user")
    return TokenResponse(access_token=create_access_token(user))
