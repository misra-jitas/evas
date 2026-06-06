"""Polling worker for processing_jobs.

A single loop claims queued jobs (FOR UPDATE SKIP LOCKED), dispatches by
job_type, and on failure either re-queues (retry) or dead-letters once
attempts reach max_attempts.
"""

from __future__ import annotations

import datetime
import logging
import time
import uuid

from sqlalchemy import select

from evas.config import get_settings
from evas.db import session_scope
from evas.enums import JobStatus
from evas.models import ProcessingJob
from evas.pipeline import HANDLERS

log = logging.getLogger("evas.worker")


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _claim_job() -> uuid.UUID | None:
    """Atomically claim the oldest queued job; mark it running, bump attempts."""
    with session_scope() as session:
        job = session.scalars(
            select(ProcessingJob)
            .where(ProcessingJob.status == JobStatus.queued)
            .order_by(ProcessingJob.queued_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).first()
        if job is None:
            return None
        job.status = JobStatus.running
        job.attempts += 1
        job.started_at = _now()
        job.finished_at = None
        return job.id


def _run_job(job_id: uuid.UUID) -> None:
    with session_scope() as session:
        job = session.get(ProcessingJob, job_id)
        if job is None:
            return
        handler = HANDLERS.get(job.job_type)
        if handler is None:
            raise RuntimeError(f"no handler for job_type={job.job_type}")
        handler(session, job)
        job.status = JobStatus.done
        job.finished_at = _now()
        job.last_error = None


def _mark_failure(job_id: uuid.UUID, error: str) -> str:
    with session_scope() as session:
        job = session.get(ProcessingJob, job_id)
        if job is None:
            return "missing"
        job.last_error = error
        job.finished_at = _now()
        if job.attempts >= job.max_attempts:
            job.status = JobStatus.dead
        else:
            job.status = JobStatus.queued  # retry on a later poll
        return job.status.value


def run_once() -> bool:
    """Claim and process a single job. Returns True if a job was handled."""
    job_id = _claim_job()
    if job_id is None:
        return False
    try:
        _run_job(job_id)
        log.info("job %s done", job_id)
    except Exception as exc:  # noqa: BLE001 - worker must not crash on handler errors
        outcome = _mark_failure(job_id, repr(exc))
        log.warning("job %s failed (%s): %r", job_id, outcome, exc)
    return True


def run_forever() -> None:
    settings = get_settings()
    log.info("worker started; polling every %.1fs", settings.worker_poll_interval_seconds)
    while True:
        worked = False
        for _ in range(settings.worker_batch_size):
            if not run_once():
                break
            worked = True
        if not worked:
            time.sleep(settings.worker_poll_interval_seconds)
