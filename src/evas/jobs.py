"""Helpers for enqueuing pipeline steps as processing_jobs rows."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from evas.enums import JobType
from evas.models import ProcessingJob


def enqueue(
    session: Session,
    *,
    job_type: JobType,
    video_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    max_attempts: int = 3,
) -> ProcessingJob:
    """Create a queued job. Does not commit (caller owns the transaction)."""
    job = ProcessingJob(
        video_id=video_id,
        job_type=job_type,
        payload=payload or {},
        max_attempts=max_attempts,
    )
    session.add(job)
    return job
