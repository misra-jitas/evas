"""Pipeline step handlers, keyed by job_type."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from evas.enums import JobType
from evas.models import ProcessingJob
from evas.pipeline.extract import handle_extract_frames
from evas.pipeline.ingest import handle_ingest
from evas.pipeline.retention import handle_archive, handle_purge_frames
from evas.pipeline.review import handle_ai_review
from evas.webhooks import handle_notify

Handler = Callable[[Session, ProcessingJob], None]

HANDLERS: dict[JobType, Handler] = {
    JobType.ingest: handle_ingest,
    JobType.extract_frames: handle_extract_frames,
    JobType.ai_review: handle_ai_review,
    JobType.notify: handle_notify,
    JobType.purge_frames: handle_purge_frames,
    JobType.archive: handle_archive,
}

__all__ = ["HANDLERS", "Handler"]
