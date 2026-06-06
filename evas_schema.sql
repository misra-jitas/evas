-- ============================================================
-- EVAS — Egocentric Video Audit System
-- Postgres schema v1. Source of truth for the data model.
-- Conventions: UUID PKs, soft deletes via deleted_at,
-- all timestamps timestamptz, JSONB for flexible/per-client config.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto"; -- gen_random_uuid()

-- ---------- ENUMS ----------
CREATE TYPE user_role        AS ENUM ('admin', 'reviewer', 'client_viewer');
CREATE TYPE video_status     AS ENUM ('ingested', 'frames_extracted', 'ai_reviewed', 'human_reviewed', 'done', 'failed');
CREATE TYPE video_priority   AS ENUM ('low', 'normal', 'high', 'rush');
CREATE TYPE grading_mode     AS ENUM ('derived', 'holistic');  -- derived = computed from weighted checklist items
CREATE TYPE run_status       AS ENUM ('queued', 'running', 'completed', 'failed');
CREATE TYPE review_status    AS ENUM ('assigned', 'in_progress', 'done');
CREATE TYPE job_status       AS ENUM ('queued', 'running', 'done', 'failed', 'dead');
CREATE TYPE job_type         AS ENUM ('ingest', 'extract_frames', 'ai_review', 'notify', 'archive', 'purge_frames');

-- ---------- TENANCY & PEOPLE ----------
CREATE TABLE clients (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name            text NOT NULL,
    slug            text NOT NULL UNIQUE,
    -- per-client sampling defaults: {"interval_seconds": 5, "max_frames": 300, "frame_width": 1280}
    sampling_config jsonb NOT NULL DEFAULT '{"interval_seconds": 5, "max_frames": 300, "frame_width": 1280}',
    -- storage lifecycle: delete extracted frames after N days, archive source video after N days (null = keep)
    frame_retention_days  int,
    video_archive_days    int,
    created_at      timestamptz NOT NULL DEFAULT now(),
    deleted_at      timestamptz
);

CREATE TABLE users (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id   uuid REFERENCES clients(id),   -- NULL = internal staff
    email       text NOT NULL UNIQUE,
    full_name   text NOT NULL,
    role        user_role NOT NULL,
    is_active   boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------- CHECKLISTS (versioned; reviews always reference an exact version) ----------
CREATE TABLE checklists (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id     uuid NOT NULL REFERENCES clients(id),
    name          text NOT NULL,
    version       int  NOT NULL,
    grading_mode  grading_mode NOT NULL DEFAULT 'derived',
    -- items: [{"key":"two_hands","label":"Two hands visible","type":"boolean","weight":1.0},
    --         {"key":"holding_tool","label":"Hand holding tool","type":"boolean","weight":2.0}, ...]
    items         jsonb NOT NULL,
    is_active     boolean NOT NULL DEFAULT true,   -- only one active version per (client, name)
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (client_id, name, version)
);
CREATE INDEX idx_checklists_client_active ON checklists (client_id) WHERE is_active;

-- ---------- VIDEOS ----------
CREATE TABLE videos (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id         uuid NOT NULL REFERENCES clients(id),
    external_ref      text,                  -- client's own ID, e.g. "00043"
    original_filename text,
    source_uri        text NOT NULL,         -- s3://... or drive://... as registered by ingestion adapter
    file_hash         text NOT NULL,         -- sha256, dedup
    size_bytes        bigint,
    duration_seconds  numeric(10,3),
    fps               numeric(7,3),
    width             int,
    height            int,
    codec             text,
    metadata          jsonb NOT NULL DEFAULT '{}',     -- anything else ffprobe returns
    sampling_override jsonb,                 -- per-video override of client sampling_config
    status            video_status NOT NULL DEFAULT 'ingested',
    priority          video_priority NOT NULL DEFAULT 'normal',
    uploaded_at       timestamptz NOT NULL DEFAULT now(),
    deleted_at        timestamptz,
    UNIQUE (client_id, file_hash)            -- idempotent ingestion
);
CREATE INDEX idx_videos_client_status ON videos (client_id, status) WHERE deleted_at IS NULL;
CREATE INDEX idx_videos_priority ON videos (priority, uploaded_at) WHERE deleted_at IS NULL;

-- ---------- FRAMES ----------
CREATE TABLE frames (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id          uuid NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    frame_index       int  NOT NULL,            -- 0-based order
    timecode_seconds  numeric(10,3) NOT NULL,   -- exact position in video
    timecode_label    text NOT NULL,            -- "HH:MM:SS.mmm" for humans
    image_uri         text NOT NULL,            -- s3://...
    purged            boolean NOT NULL DEFAULT false,  -- image deleted by retention policy, row kept
    created_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (video_id, frame_index)
);
CREATE INDEX idx_frames_video ON frames (video_id);

-- ---------- FUTURE: temporal review (sequences, not stills). Minimal now, real later. ----------
CREATE TABLE clips (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id        uuid NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    start_seconds   numeric(10,3) NOT NULL,
    end_seconds     numeric(10,3) NOT NULL,
    label           text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- ---------- AI REVIEWS (a run = one model+prompt pass over a video; re-runs keep history) ----------
CREATE TABLE ai_runs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id        uuid NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    checklist_id    uuid NOT NULL REFERENCES checklists(id),  -- exact version used
    model           text NOT NULL,             -- e.g. "claude-haiku-4-5-20251001"
    prompt_version  text NOT NULL,             -- git tag / semver of the prompt template
    status          run_status NOT NULL DEFAULT 'queued',
    grade           numeric(4,2),              -- 0–10, video-level
    summary         text,
    tokens_in       bigint NOT NULL DEFAULT 0,
    tokens_out      bigint NOT NULL DEFAULT 0,
    cost_usd        numeric(10,6) NOT NULL DEFAULT 0,   -- per-client cost/margin tracking
    error           text,
    started_at      timestamptz,
    completed_at    timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_ai_runs_video ON ai_runs (video_id, created_at DESC);

CREATE TABLE ai_frame_findings (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ai_run_id    uuid NOT NULL REFERENCES ai_runs(id) ON DELETE CASCADE,
    frame_id     uuid NOT NULL REFERENCES frames(id) ON DELETE CASCADE,
    description  text,
    -- findings mirror checklist item keys: {"two_hands": {"value": true, "confidence": 0.97}, ...}
    findings     jsonb NOT NULL,
    confidence   numeric(4,3),              -- min/avg confidence across items, for flagging
    flagged      boolean NOT NULL DEFAULT false,  -- below threshold → human attention
    UNIQUE (ai_run_id, frame_id)
);
CREATE INDEX idx_aff_run ON ai_frame_findings (ai_run_id);
CREATE INDEX idx_aff_flagged ON ai_frame_findings (ai_run_id) WHERE flagged;

-- ---------- HUMAN REVIEWS ----------
CREATE TABLE human_reviews (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id      uuid NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    checklist_id  uuid NOT NULL REFERENCES checklists(id),
    reviewer_id   uuid NOT NULL REFERENCES users(id),
    is_qa_review  boolean NOT NULL DEFAULT false,   -- second-pass QA on another human's review
    qa_of_review  uuid REFERENCES human_reviews(id),
    status        review_status NOT NULL DEFAULT 'assigned',
    grade         numeric(4,2),              -- NULL = not graded yet
    notes         text,
    assigned_at   timestamptz NOT NULL DEFAULT now(),
    reviewed_at   timestamptz
);
CREATE INDEX idx_hr_video ON human_reviews (video_id);
CREATE INDEX idx_hr_reviewer_queue ON human_reviews (reviewer_id, status) WHERE status <> 'done';

CREATE TABLE human_frame_notes (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    human_review_id    uuid NOT NULL REFERENCES human_reviews(id) ON DELETE CASCADE,
    frame_id           uuid NOT NULL REFERENCES frames(id) ON DELETE CASCADE,
    note               text,
    -- human corrections to AI findings, same shape as ai findings JSON
    override_findings  jsonb,
    created_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (human_review_id, frame_id)
);

-- ---------- JOBS (every pipeline step is a job: idempotent, retried, dead-lettered) ----------
CREATE TABLE processing_jobs (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id     uuid REFERENCES videos(id) ON DELETE CASCADE,
    job_type     job_type NOT NULL,
    status       job_status NOT NULL DEFAULT 'queued',
    attempts     int NOT NULL DEFAULT 0,
    max_attempts int NOT NULL DEFAULT 3,
    payload      jsonb NOT NULL DEFAULT '{}',
    last_error   text,
    queued_at    timestamptz NOT NULL DEFAULT now(),
    started_at   timestamptz,
    finished_at  timestamptz
);
CREATE INDEX idx_jobs_pickup ON processing_jobs (status, queued_at) WHERE status = 'queued';
CREATE INDEX idx_jobs_video ON processing_jobs (video_id);

-- ---------- AUDIT ----------
CREATE TABLE audit_log (
    id           bigserial PRIMARY KEY,
    user_id      uuid REFERENCES users(id),   -- NULL = system
    entity_type  text NOT NULL,               -- 'video' | 'human_review' | 'checklist' | ...
    entity_id    uuid NOT NULL,
    action       text NOT NULL,               -- 'grade_changed' | 'status_changed' | ...
    old_value    jsonb,
    new_value    jsonb,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_entity ON audit_log (entity_type, entity_id);

-- ---------- NOTIFICATIONS / WEBHOOKS ----------
CREATE TABLE webhook_endpoints (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id   uuid NOT NULL REFERENCES clients(id),
    url         text NOT NULL,
    secret      text NOT NULL,                 -- HMAC signing
    events      text[] NOT NULL DEFAULT '{video.ai_reviewed, video.human_reviewed}',
    is_active   boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE webhook_deliveries (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint_id   uuid NOT NULL REFERENCES webhook_endpoints(id),
    event         text NOT NULL,
    payload       jsonb NOT NULL,
    status_code   int,
    attempts      int NOT NULL DEFAULT 0,
    delivered_at  timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- ---------- CONVENIENCE VIEW: video review board ----------
CREATE VIEW video_review_board AS
SELECT
    v.id,
    v.client_id,
    v.external_ref,
    v.status,
    v.priority,
    latest_ai.grade   AS ai_grade,
    latest_ai.model   AS ai_model,
    hr.grade          AS human_grade,        -- NULL = not graded yet
    hr.reviewer_id,
    CASE
        WHEN latest_ai.grade IS NOT NULL AND hr.grade IS NOT NULL
        THEN abs(latest_ai.grade - hr.grade)
    END AS grade_discrepancy,
    v.uploaded_at
FROM videos v
LEFT JOIN LATERAL (
    SELECT grade, model FROM ai_runs
    WHERE ai_runs.video_id = v.id AND ai_runs.status = 'completed'
    ORDER BY completed_at DESC LIMIT 1
) latest_ai ON true
LEFT JOIN LATERAL (
    SELECT grade, reviewer_id FROM human_reviews
    WHERE human_reviews.video_id = v.id AND NOT is_qa_review
    ORDER BY reviewed_at DESC NULLS LAST LIMIT 1
) hr ON true
WHERE v.deleted_at IS NULL;
