"""Ops/admin endpoints: operational metrics for alerting dashboards."""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from evas.auth import require_roles
from evas.db import get_session
from evas.enums import JobStatus, RunStatus, UserRole
from evas.models import AiRun, ProcessingJob, User, Video, WebhookDelivery

router = APIRouter(prefix="/admin", tags=["admin"])
_admin = require_roles(UserRole.admin)


@router.get("/metrics")
def metrics(
    session: Session = Depends(get_session),
    user: User = Depends(_admin),
    cost_spike_pct: float = Query(50.0, description="Day-over-day cost increase % to flag"),
) -> dict[str, Any]:
    # Job queue health.
    job_counts: dict[JobStatus, int] = {
        row[0]: row[1]
        for row in session.execute(
            select(ProcessingJob.status, func.count()).group_by(ProcessingJob.status)
        ).all()
    }
    dead_jobs = int(job_counts.get(JobStatus.dead, 0))
    queue_depth = int(job_counts.get(JobStatus.queued, 0))

    # Webhook delivery failures (attempted, not delivered).
    webhook_failures = int(
        session.scalar(
            select(func.count())
            .select_from(WebhookDelivery)
            .where(WebhookDelivery.delivered_at.is_(None), WebhookDelivery.attempts > 0)
        )
        or 0
    )

    # Day-over-day cost spikes per client.
    now = datetime.datetime.now(datetime.UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yest_start = today_start - datetime.timedelta(days=1)

    def _cost_by_client(start: datetime.datetime, end: datetime.datetime) -> dict[Any, float]:
        rows = session.execute(
            select(Video.client_id, func.coalesce(func.sum(AiRun.cost_usd), 0))
            .select_from(AiRun)
            .join(Video, Video.id == AiRun.video_id)
            .where(
                AiRun.status == RunStatus.completed,
                AiRun.completed_at >= start,
                AiRun.completed_at < end,
            )
            .group_by(Video.client_id)
        ).all()
        return {cid: float(c) for cid, c in rows}

    today = _cost_by_client(today_start, now)
    yesterday = _cost_by_client(yest_start, today_start)
    spikes: list[dict[str, Any]] = []
    for cid, today_cost in today.items():
        prior = yesterday.get(cid, 0.0)
        if prior == 0 and today_cost > 0:
            pct = None  # new spend (no prior-day baseline)
        elif prior > 0:
            pct = (today_cost - prior) / prior * 100
        else:
            continue
        if pct is None or pct >= cost_spike_pct:
            spikes.append(
                {
                    "client_id": str(cid),
                    "today_cost": round(today_cost, 6),
                    "yesterday_cost": round(prior, 6),
                    "pct_change": None if pct is None else round(pct, 1),
                }
            )

    return {
        "dead_jobs": dead_jobs,
        "queue_depth": queue_depth,
        "running_jobs": int(job_counts.get(JobStatus.running, 0)),
        "webhook_failures": webhook_failures,
        "cost_spikes": spikes,
    }
