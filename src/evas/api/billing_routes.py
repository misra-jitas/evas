"""Billing report endpoint: JSON / CSV / PDF, per client per month."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from evas.auth import assert_can_access_client, get_current_user
from evas.billing import compute_billing, to_csv, to_pdf
from evas.db import get_session
from evas.models import User

router = APIRouter(tags=["billing"])


def _parse_period(period: str) -> tuple[int, int]:
    try:
        year_s, month_s = period.split("-")
        year, month = int(year_s), int(month_s)
        if not 1 <= month <= 12:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="period must be YYYY-MM") from exc
    return year, month


@router.get("/clients/{client_id}/billing")
def get_billing(
    client_id: uuid.UUID,
    period: str = Query(..., description="Billing month as YYYY-MM"),
    format: str = Query("json", pattern="^(json|csv|pdf)$"),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Any:
    assert_can_access_client(user, client_id)
    year, month = _parse_period(period)
    try:
        report = compute_billing(session, client_id, year, month)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if format == "csv":
        return Response(
            content=to_csv(report),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=billing_{period}.csv"},
        )
    if format == "pdf":
        return Response(
            content=to_pdf(report),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=billing_{period}.pdf"},
        )
    return asdict(report)
