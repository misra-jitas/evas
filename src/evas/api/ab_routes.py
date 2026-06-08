"""Prompt A/B endpoints (admin): run two prompt versions and compare."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from evas.ab import compare, enqueue_ab_runs
from evas.api.schemas import AbRequest
from evas.auth import require_roles
from evas.db import get_session
from evas.enums import UserRole
from evas.models import User

router = APIRouter(prefix="/ab-tests", tags=["prompt-ab"])
_admin = require_roles(UserRole.admin)


@router.post("", status_code=202)
def start_ab_test(
    req: AbRequest,
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
) -> dict[str, Any]:
    """Enqueue a frame review per (video, prompt version)."""
    jobs = enqueue_ab_runs(session, req.video_ids, req.prompt_version_a, req.prompt_version_b)
    return {"jobs_enqueued": jobs}


@router.post("/compare")
def compare_ab(
    req: AbRequest,
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
) -> dict[str, Any]:
    """Comparison report between the two prompt versions over the video set."""
    return compare(session, req.video_ids, req.prompt_version_a, req.prompt_version_b)
