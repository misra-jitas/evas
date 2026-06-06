# EVAS — Egocentric Video Audit System (kickoff prompt for Claude Code)

Build **EVAS**, a multi-client video review platform: ingest videos, extract frames, AI-review each frame against a per-client checklist, then human review with grades and notes.

## Source of truth
`evas_schema.sql` in this repo is the complete data model. Read it first — it encodes all product decisions (versioned checklists, AI runs with history, human reviews + QA, jobs, audit, webhooks, retention). Do not redesign it; ask before changing it.

## Stack
- Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, Postgres 16
- S3 for videos + frames, `ffmpeg`/`ffprobe` for extraction
- Worker: simple polling loop on `processing_jobs` table (no SQS yet)
- AI: Anthropic API, vision, model `claude-haiku-4-5`; prompt templates versioned in `prompts/` with semver filenames
- Terraform lives in `infra/evas/` with its own state — never touch other roots

## Pipeline (each step = a row in processing_jobs, idempotent, retries→dead)
1. **ingest** — register video (hash dedup per client), ffprobe metadata → status `ingested`
2. **extract_frames** — sample per client `sampling_config` (or video override), upload frames to S3, record timecode → `frames_extracted`
3. **ai_review** — create `ai_runs` row; per frame: send image + checklist items → JSON findings {value, confidence} per item + description; flag low-confidence frames; compute video grade per checklist `grading_mode`; track tokens/cost → `ai_reviewed`
4. **notify** — webhook deliveries for subscribed events

## Milestone 1 (build only this)
- Alembic migration from `evas_schema.sql`
- Ingestion: CLI batch import (CSV of S3 URIs) + POST /videos endpoint
- Frame extraction worker
- AI review worker with one example checklist (two_hands, holding_tool, at_workstation, holding_broom)
- GET endpoints: video list (use `video_review_board` view), video detail with frames + findings
- Findings export: JSON file per video

Defer: auth, human review UI, webhooks delivery, clips. Schema supports them; do not implement yet.

## Rules
- Every status change → `audit_log`
- Never overwrite AI results — new run, new rows
- Config via env vars, 12-factor; no secrets in code
