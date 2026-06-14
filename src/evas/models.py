"""SQLAlchemy ORM models mapped onto the schema in evas_schema.sql.

These are for ORM use by the API, workers, and CLI. The schema is owned by
the Alembic migration (which reproduces evas_schema.sql); these models must
not be used to autogenerate migrations.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from evas import enums
from evas.db import Base


def _pg_enum(py_enum: type, name: str) -> ENUM:
    # Reference the DB type created by the migration; never (re)create it here.
    return ENUM(
        py_enum, name=name, create_type=False, values_callable=lambda e: [m.value for m in e]
    )


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


_now = text("now()")


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    sampling_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    frame_retention_days: Mapped[int | None] = mapped_column(Integer)
    video_archive_days: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now
    )
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    client_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clients.id"))
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[enums.UserRole] = mapped_column(
        _pg_enum(enums.UserRole, "user_role"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now
    )


class Checklist(Base):
    __tablename__ = "checklists"
    __table_args__ = (UniqueConstraint("client_id", "name", "version"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    grading_mode: Mapped[enums.GradingMode] = mapped_column(
        _pg_enum(enums.GradingMode, "grading_mode"),
        nullable=False,
        server_default=text("'derived'"),
    )
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    prompt_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now
    )


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (UniqueConstraint("client_id", "file_hash"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sources.id"))
    external_ref: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str | None] = mapped_column(Text)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    duration_seconds: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    fps: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    codec: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'")
    )
    sampling_override: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[enums.VideoStatus] = mapped_column(
        _pg_enum(enums.VideoStatus, "video_status"),
        nullable=False,
        server_default=text("'ingested'"),
    )
    priority: Mapped[enums.VideoPriority] = mapped_column(
        _pg_enum(enums.VideoPriority, "video_priority"),
        nullable=False,
        server_default=text("'normal'"),
    )
    uploaded_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now
    )
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    frames: Mapped[list[Frame]] = relationship(back_populates="video")


class Frame(Base):
    __tablename__ = "frames"
    __table_args__ = (UniqueConstraint("video_id", "frame_index"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    frame_index: Mapped[int] = mapped_column(Integer, nullable=False)
    timecode_seconds: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    timecode_label: Mapped[str] = mapped_column(Text, nullable=False)
    image_uri: Mapped[str] = mapped_column(Text, nullable=False)
    purged: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now
    )

    video: Mapped[Video] = relationship(back_populates="frames")


class AiRun(Base):
    __tablename__ = "ai_runs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    checklist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("checklists.id"), nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[enums.RunStatus] = mapped_column(
        _pg_enum(enums.RunStatus, "run_status"), nullable=False, server_default=text("'queued'")
    )
    grade: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    summary: Mapped[str | None] = mapped_column(Text)
    tokens_in: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    tokens_out: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, server_default=text("0")
    )
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now
    )

    findings: Mapped[list[AiFrameFinding]] = relationship(back_populates="ai_run")


class AiFrameFinding(Base):
    __tablename__ = "ai_frame_findings"
    __table_args__ = (UniqueConstraint("ai_run_id", "frame_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    ai_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_runs.id", ondelete="CASCADE"), nullable=False
    )
    frame_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("frames.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text)
    findings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    ai_run: Mapped[AiRun] = relationship(back_populates="findings")
    frame: Mapped[Frame] = relationship()


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    video_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    job_type: Mapped[enums.JobType] = mapped_column(
        _pg_enum(enums.JobType, "job_type"), nullable=False
    )
    status: Mapped[enums.JobStatus] = mapped_column(
        _pg_enum(enums.JobStatus, "job_status"), nullable=False, server_default=text("'queued'")
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'")
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    queued_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now
    )
    started_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    finished_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now
    )


class HumanReview(Base):
    __tablename__ = "human_reviews"

    id: Mapped[uuid.UUID] = _uuid_pk()
    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    checklist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("checklists.id"), nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    is_qa_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    qa_of_review: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("human_reviews.id"))
    status: Mapped[enums.ReviewStatus] = mapped_column(
        _pg_enum(enums.ReviewStatus, "review_status"),
        nullable=False,
        server_default=text("'assigned'"),
    )
    grade: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    assigned_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now
    )
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class HumanFrameNote(Base):
    __tablename__ = "human_frame_notes"
    __table_args__ = (UniqueConstraint("human_review_id", "frame_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    human_review_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("human_reviews.id", ondelete="CASCADE"), nullable=False
    )
    frame_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("frames.id", ondelete="CASCADE"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text)
    override_findings: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now
    )


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id: Mapped[uuid.UUID] = _uuid_pk()
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    secret: Mapped[str] = mapped_column(Text, nullable=False)
    events: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now
    )


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[uuid.UUID] = _uuid_pk()
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_endpoints.id"), nullable=False
    )
    event: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    delivered_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now
    )


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("client_id", "uri_prefix"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[enums.SourceType] = mapped_column(
        _pg_enum(enums.SourceType, "source_type"), nullable=False
    )
    uri_prefix: Mapped[str] = mapped_column(Text, nullable=False)
    credential_ref: Mapped[str | None] = mapped_column(Text)
    sampling_override: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[enums.SourceStatus] = mapped_column(
        _pg_enum(enums.SourceStatus, "source_status"),
        nullable=False,
        server_default=text("'connected'"),
    )
    auto_sync: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    last_synced_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_sync_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now
    )
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[uuid.UUID] = _uuid_pk()
    video_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    start_seconds: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    end_seconds: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    label: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=_now
    )


class AiClipFinding(Base):
    __tablename__ = "ai_clip_findings"
    __table_args__ = (UniqueConstraint("ai_run_id", "clip_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    ai_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_runs.id", ondelete="CASCADE"), nullable=False
    )
    clip_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clips.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text)
    findings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
