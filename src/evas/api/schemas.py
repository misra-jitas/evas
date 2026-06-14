"""Pydantic request/response models for the HTTP API."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from pydantic import BaseModel, Field

from evas.enums import ReviewStatus, SourceType, VideoPriority


class VideoCreateRequest(BaseModel):
    client_id: uuid.UUID
    source_uri: str = Field(..., description="s3://bucket/key of the source video")
    external_ref: str | None = None
    original_filename: str | None = None
    sampling_override: dict[str, Any] | None = None
    priority: VideoPriority = VideoPriority.normal


class JobAccepted(BaseModel):
    job_id: uuid.UUID
    job_type: str
    status: str


class ReviewBoardRow(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    external_ref: str | None
    status: str
    priority: str
    ai_grade: float | None
    ai_model: str | None
    human_grade: float | None
    reviewer_id: uuid.UUID | None
    grade_discrepancy: float | None
    uploaded_at: datetime.datetime
    source_id: uuid.UUID | None = None
    source_label: str | None = None
    original_filename: str | None = None
    duration_seconds: float | None = None
    frame_count: int = 0
    checklist_name: str | None = None


class FrameFindingOut(BaseModel):
    frame_id: uuid.UUID  # real frame id, for targeting human-review frame overrides
    frame_index: int
    timecode_seconds: float
    timecode_label: str
    image_uri: str
    image_url: str | None = None  # presigned, browser-fetchable; null if purged
    purged: bool
    description: str | None = None
    findings: dict[str, Any] | None = None
    confidence: float | None = None
    flagged: bool | None = None


class AiRunOut(BaseModel):
    id: uuid.UUID
    model: str
    prompt_version: str
    checklist_id: uuid.UUID
    status: str
    grade: float | None
    summary: str | None
    tokens_in: int
    tokens_out: int
    cost_usd: float
    completed_at: datetime.datetime | None


class VideoDetail(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    external_ref: str | None
    original_filename: str | None
    source_uri: str
    status: str
    priority: str
    duration_seconds: float | None
    fps: float | None
    width: int | None
    height: int | None
    latest_ai_run: AiRunOut | None
    checklist_items: list[dict[str, Any]] | None = None
    frames: list[FrameFindingOut]


# ---- Auth ----
class TokenRequest(BaseModel):
    email: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---- Human review ----
class HumanReviewCreate(BaseModel):
    reviewer_id: uuid.UUID | None = Field(
        None, description="Reviewer to assign; defaults to the caller (self-assign)."
    )


class HumanReviewUpdate(BaseModel):
    status: ReviewStatus | None = None
    grade: float | None = Field(None, ge=0, le=10)
    notes: str | None = None


class HumanReviewOut(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    checklist_id: uuid.UUID
    reviewer_id: uuid.UUID
    is_qa_review: bool
    qa_of_review: uuid.UUID | None
    status: str
    grade: float | None
    notes: str | None
    assigned_at: datetime.datetime
    reviewed_at: datetime.datetime | None


class FrameNoteUpsert(BaseModel):
    note: str | None = None
    override_findings: dict[str, Any] | None = None


# ---- Prompt A/B ----
class AbRequest(BaseModel):
    video_ids: list[uuid.UUID]
    prompt_version_a: str
    prompt_version_b: str


# ---- Clips (temporal review) ----
class ClipCreate(BaseModel):
    start_seconds: float = Field(..., ge=0)
    end_seconds: float = Field(..., ge=0)
    label: str | None = None


class ClipOut(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    start_seconds: float
    end_seconds: float
    label: str | None
    description: str | None = None
    findings: dict[str, Any] | None = None
    confidence: float | None = None
    flagged: bool | None = None


# ---- Webhooks ----
class WebhookCreate(BaseModel):
    url: str
    secret: str
    events: list[str] | None = None


class WebhookOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    url: str
    events: list[str]
    is_active: bool
    created_at: datetime.datetime


# ---- Clients ----
class ClientCreate(BaseModel):
    name: str
    slug: str
    sampling_config: dict[str, Any] | None = None
    frame_retention_days: int | None = None
    video_archive_days: int | None = None


class ClientUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    sampling_config: dict[str, Any] | None = None
    frame_retention_days: int | None = None
    video_archive_days: int | None = None


class ClientOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    sampling_config: dict[str, Any]
    frame_retention_days: int | None
    video_archive_days: int | None
    created_at: datetime.datetime
    video_count: int


# ---- AI Monitor ----
class RerunRequest(BaseModel):
    prompt_version: str | None = None
    checklist_id: uuid.UUID | None = None


class SendToHumanRequest(BaseModel):
    reviewer_id: uuid.UUID


# ---- Checklists (review config: items + prompt framing) ----
class ChecklistSave(BaseModel):
    name: str
    items: list[dict[str, Any]]
    prompt_template: str | None = None
    grading_mode: str = "derived"


class ChecklistOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    name: str
    version: int
    grading_mode: str
    items: list[dict[str, Any]]
    prompt_template: str | None
    is_active: bool
    created_at: datetime.datetime


# ---- Sources ----
class SourceCreate(BaseModel):
    client_id: uuid.UUID
    label: str
    type: SourceType = SourceType.s3
    uri_prefix: str = Field(..., description="s3://bucket/prefix/ or https://...")
    credential_ref: str | None = Field(
        None, description="Name/ARN of a stored secret — never the secret itself."
    )
    sampling_override: dict[str, Any] | None = None
    auto_sync: bool = False
    scan_now: bool = Field(True, description="Enqueue an immediate sync on registration.")


class SourceUpdate(BaseModel):
    label: str | None = None
    credential_ref: str | None = None
    sampling_override: dict[str, Any] | None = None
    auto_sync: bool | None = None
    enabled: bool | None = Field(
        None, description="Enable (connected) or disable (disabled) the source."
    )


class SourceFunnel(BaseModel):
    total: int
    to_ingest: int
    ingested: int
    in_review: int
    done: int
    failed: int


class SourceOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    label: str
    type: str
    uri_prefix: str
    credential_ref: str | None
    sampling_override: dict[str, Any] | None
    status: str
    auto_sync: bool
    last_synced_at: datetime.datetime | None
    last_error: str | None
    last_sync_result: dict[str, Any] | None
    created_at: datetime.datetime
    funnel: SourceFunnel
