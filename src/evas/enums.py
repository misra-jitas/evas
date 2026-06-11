"""Python mirrors of the Postgres ENUM types defined in evas_schema.sql.

Values must match the SQL enum labels exactly.
"""

from __future__ import annotations

import enum


class UserRole(enum.StrEnum):
    admin = "admin"
    reviewer = "reviewer"
    client_viewer = "client_viewer"


class VideoStatus(enum.StrEnum):
    ingested = "ingested"
    frames_extracted = "frames_extracted"
    ai_reviewed = "ai_reviewed"
    human_reviewed = "human_reviewed"
    done = "done"
    failed = "failed"


class VideoPriority(enum.StrEnum):
    low = "low"
    normal = "normal"
    high = "high"
    rush = "rush"


class GradingMode(enum.StrEnum):
    derived = "derived"  # computed from weighted checklist items
    holistic = "holistic"


class RunStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class ReviewStatus(enum.StrEnum):
    assigned = "assigned"
    in_progress = "in_progress"
    done = "done"


class JobStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"
    dead = "dead"


class JobType(enum.StrEnum):
    ingest = "ingest"
    extract_frames = "extract_frames"
    ai_review = "ai_review"
    notify = "notify"
    archive = "archive"
    purge_frames = "purge_frames"
    sync_source = "sync_source"


class SourceType(enum.StrEnum):
    s3 = "s3"
    url = "url"  # extend later: gdrive, gcs, azure


class SourceStatus(enum.StrEnum):
    connected = "connected"
    syncing = "syncing"
    error = "error"
    disabled = "disabled"
