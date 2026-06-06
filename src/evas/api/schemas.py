"""Pydantic request/response models for the HTTP API."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from pydantic import BaseModel, Field

from evas.enums import VideoPriority


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
