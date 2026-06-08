"""Pydantic request/response models for the HTTP API."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from pydantic import BaseModel, Field

from evas.enums import ReviewStatus, VideoPriority


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


class FrameFindingOut(BaseModel):
    frame_index: int
    timecode_seconds: float
    timecode_label: str
    image_uri: str
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
