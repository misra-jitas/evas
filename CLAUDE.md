# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

EVAS (Egocentric Video Audit System) — a multi-client platform that ingests videos, extracts frames, AI-reviews each frame against a per-client checklist, then supports human review with grades and notes. See `@EVAS_KICKOFF.md` for full product context.

Milestone 1 is implemented: code lives in `src/evas/` (config, db, models, pipeline handlers, worker, API, CLI), the Alembic migration in `alembic/`, and tests in `tests/`.

## Source of truth

`evas_schema.sql` is the complete, locked data model (Postgres 16). **Read it before writing any code that touches data.** It encodes product decisions — versioned checklists, AI runs with history, human reviews + QA, jobs, audit, webhooks, retention. **Do not redesign it; ask before changing it.** Alembic migrations must reproduce this schema, not diverge from it.

## Stack

- Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, Postgres 16
- S3 for videos + frames; `ffmpeg`/`ffprobe` for extraction
- Worker: a simple polling loop on the `processing_jobs` table (no SQS/Celery yet)
- AI: Anthropic API, vision, model `claude-haiku-4-5`; prompt templates versioned in `prompts/` with semver filenames
- Terraform lives in `infra/evas/` with its own state — **never touch other Terraform roots**

## Pipeline

Each step is a row in `processing_jobs`: idempotent, retried up to `max_attempts`, then dead-lettered (`status = 'dead'`).
1. **ingest** — register video (sha256 hash dedup per client via `UNIQUE (client_id, file_hash)`), ffprobe metadata → status `ingested`
2. **extract_frames** — sample per client `sampling_config` (or per-video `sampling_override`), upload frames to S3, record timecode → `frames_extracted`
3. **ai_review** — create an `ai_runs` row; per frame send image + checklist items → JSON findings `{value, confidence}` per item; flag low-confidence frames; compute video grade per checklist `grading_mode`; track tokens/cost → `ai_reviewed`
4. **notify** — webhook deliveries for subscribed events

## Milestone 1 — build only this

- Alembic migration reproducing `evas_schema.sql`
- Ingestion: CLI batch import (CSV of S3 URIs) + `POST /videos`
- Frame extraction worker
- AI review worker with one example checklist (`two_hands`, `holding_tool`, `at_workstation`, `holding_broom`)
- GET endpoints: video list (use the `video_review_board` view), video detail with frames + findings
- Findings export: one JSON file per video

**Defer (schema supports them — do not implement yet):** auth, human review UI, webhook delivery, clips.

## Milestone 2 — implemented (see `@Evas2.md`)

- **Auth** — stateless JWT (`evas/auth.py`). The `users` table has **no password column** and the schema is locked, so credentials are not stored: tokens are signed with `EVAS_JWT_SECRET`; `POST /auth/token` is gated by `EVAS_BOOTSTRAP_TOKEN` (interim until an IdP). Roles: `admin`, `reviewer`, `client_viewer` (the latter is tenancy-scoped to its own `client_id`; cross-tenant access → 404).
- **Human review** — assign/grade/notes, frame-level `override_findings`, QA second pass (`evas/api/human_reviews.py`). Completing a non-QA review moves the video to `human_reviewed` and enqueues a `notify`.
- **Webhook delivery** — the `notify` job fans out to active endpoints, HMAC-signed (`X-EVAS-Signature`), recorded in `webhook_deliveries`, idempotent on retry (`evas/webhooks.py`). Endpoint mgmt under `/clients/{id}/webhooks` (admin).
- **Retention/archive** — `purge_frames` (delete S3 images, keep rows, `purged=true`) and `archive` jobs + `evas retention-sweep` (`evas/pipeline/retention.py`).

No new migration: the M1 migration already reproduces the whole schema (all M2 tables exist).

## Milestone 3 — implemented (see `@EVAS_3.md`, UI spec `@EVAS_UI.md`)

- **Clips (temporal review)** — `Clip`/`AiClipFinding` models; manual + auto segmentation (`evas/clips.py`, auto-splits where frame findings change); clip review reuses the `ai_review` job with `payload.target="clip"` and sends a frame *sequence* (`evas/pipeline/review.py`, `prompts/clip_review-*.txt`). Checklist items carry an optional `"scope": "frame"|"clip"`. **One schema addition**: `ai_clip_findings` (migration `0002`, also added to `evas_schema.sql`).
- **Retention** — `archive` now transitions the source video to S3 **Glacier** (`storage.set_storage_class`, recorded in `videos.metadata`); `evas retention-sweep --dry-run`; nightly cron documented in `docs/ops.md`.
- **Billing** — `evas/billing.py` + `GET /clients/{id}/billing?period=YYYY-MM&format=json|csv|pdf`. Token/cost come straight from `ai_runs` (reconciliation test). Needs `fpdf2`.
- **Prompt A/B** — `evas/ab.py` + `/ab-tests` (admin): run two `prompt_version`s (separate `ai_runs` via `payload.prompt_version`), compare grades/cost/disagreements vs human ground truth, recommend one.
- **Client portal** — `/portal/*` (read-only, tenancy-isolated): final finding = human override else AI; strips cost/reviewer/model/confidence.
- **Ops** — `GET /admin/metrics` (dead jobs, queue depth, webhook failures, cost spikes); `scripts/backup.sh`/`restore.sh`; SQS-threshold + runbook in `docs/ops.md`.

**Defer (UI build is follow-up):** the React reviewer/ops/portal frontends in `EVAS_UI.md` are not built yet — backend only this milestone. `EVAS_AI_STUB=true` runs reviews offline (frame + clip).

## Sources + AI Monitor — implemented (backend; see `@EVAS_SOURCES.md`, `@EVAS_AI_MONITOR.md`)

- **Sources** — a `source` is a pointer to a place full of videos (S3 prefix; `url` reserved). Register one and a `sync_source` worker (`evas/pipeline/sync.py`) enumerates it (`storage.list_objects`, video-extension filter), dedups against known `source_uri`s, and enqueues `ingest` per new file tagged with `source_id`. Counts (`discovered/registered/skipped/failed`) are persisted to `sources.last_sync_result` so a partial/failed scan can't look complete; `failed>0` ⇒ `status=error`. **`url` raises a clear "not yet supported"** (records the error state + commits before raising) until a listing contract exists. Endpoints `/sources` CRUD + `POST /sources/{id}/sync` (admin); list/detail carry a derived **funnel** (`to_ingest/ingested/in_review/done/failed`). `evas sync-sources` (cron, `--all`/`--dry-run`) drives nightly `auto_sync`. `GET /videos?source_id=` scopes the board.
- **AI Monitor** — admin observability over existing tables (no new data): `GET /ai/runs` (filterable run log + frames done/total, flagged, tokens, cost, duration), `GET /ai/runs/{id}` (per-frame findings, issues, cost/frame, AI-vs-human grade gap), `GET /ai/stats` (throughput/cost/confidence/flagged/error rates grouped by model & prompt_version). `POST /ai/runs/{id}/rerun` enqueues a fresh `ai_review` (new run, history preserved).
- **Schema addition** — migration `0003` adds `sources`, `videos.source_id`, the `sync_source` `job_type` value (via `autocommit_block()` — `ALTER TYPE … ADD VALUE` can't run in a txn / be used in the same txn), and appends `source_id` to the `video_review_board` view. Mirrored into `evas_schema.sql` (enum value inline there for fresh installs).

## Development

- Use the project venv: `.venv/bin/python` (created with `--system-site-packages`). `ruff` is the global install on PATH; `mypy`/`pytest` run via `.venv/bin/python -m …`.
- **Local Postgres runs in Docker on host port 5433** (5432 is taken by another project on this machine): container `evas-pg`. The DB URL is set in `.env` (gitignored; copy from `.env.example`). Config is read with the `EVAS_` env prefix.
- Migrate: `.venv/bin/python -m alembic upgrade head`. The single migration embeds `evas_schema.sql` verbatim via `exec_driver_sql` — keep it a faithful reproduction.
- Run the worker: `.venv/bin/python -m evas.cli worker` (or `drain` to process the queue once). Seed data: `evas seed-client`, batch import: `evas import-csv`.
- API: `.venv/bin/python -m uvicorn evas.api.app:app`.
- **Tests need the Docker Postgres up**; they create/migrate an isolated `evas_test` DB and truncate between tests. S3 and Anthropic are faked (no network/keys needed). Run: `.venv/bin/python -m pytest`.
- Verify before commit: `ruff check .` && `.venv/bin/python -m mypy src` && `.venv/bin/python -m pytest`.

## Non-negotiable rules

- Every status change → write an `audit_log` row (`user_id` NULL = system).
- **Never overwrite AI results** — a re-review is a new `ai_runs` row with new `ai_frame_findings`; keep history.
- Config via env vars, 12-factor; no secrets in code.
- Soft deletes via `deleted_at`; queries must respect it. Retention purges frame images but keeps the `frames` row (`purged = true`).
