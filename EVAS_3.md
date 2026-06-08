# EVAS_3 — Milestone 3: Scale, Money & Smarter Review (prompt for Claude Code)

Prerequisites: Milestones 1–2 complete (`EVAS_KICKOFF.md`, `EVAS_2.md`). `evas_schema.sql` remains the source of truth; everything below is already schema-ready. UI work follows `EVAS_UI.md` (Client Portal section). Do not change the schema; ask first.

## Build

1. **Temporal review (clips)** — activate the `clips` table:
   - Segment videos: manual (admin marks start/end) and auto (split where AI frame findings change between consecutive frames).
   - New job type for clip review: send the frame *sequence* of a clip to the model for action-level questions ("is he sweeping the floor" vs "holding a broom"). Findings attach to clips the same way `ai_frame_findings` attach to frames (add `ai_clip_findings` table mirroring it — the one allowed schema addition, propose migration first).
   - Checklist items gain an optional `"scope": "frame" | "clip"` field; clip-scoped items only evaluated on clips.
2. **Retention jobs** — implement the two job types already in the enum:
   - `purge_frames`: delete frame images from S3 after `clients.frame_retention_days`; set `frames.purged = true`, keep rows (findings stay queryable).
   - `archive`: move source video to S3 Glacier after `clients.video_archive_days`; record storage class in `videos.metadata`.
   - Nightly scheduler enqueues both per client. Dry-run flag.
3. **Client self-serve portal** — per `EVAS_UI.md` §3: read-only videos list, video detail (final findings = human override where present, else AI; no internal data), CSV export. Tenancy isolation tested again at the portal layer.
4. **Billing reports** — per client per month: videos processed, frames extracted, tokens and `cost_usd` from `ai_runs`, human review count and total review time, storage footprint. Endpoint + CSV download + simple PDF. Numbers must reconcile with raw `ai_runs` sums — write a reconciliation test.
5. **Prompt A/B** — admin tool: run two `prompt_version`s over the same video set (each = separate `ai_runs`), comparison view: grade deltas, finding disagreements, cost per version, and agreement vs human grades (ground truth). Output: a recommendation table per checklist item.
6. **Ops hardening**
   - Job queue: move from polling to SQS if daily volume exceeds what polling handles cleanly; otherwise keep polling and document the threshold.
   - Metrics + alerts: dead jobs, webhook delivery failures, cost spike per client (day-over-day > X%), queue depth.
   - Backup/restore: automated Postgres snapshots, restore procedure tested and documented.

## Defer to Milestone 4 (if ever)
Client self-upload UI · auto-checklist suggestions from footage · model fine-tuning on human overrides · frame annotation drawing (integrate Label Studio if needed) · multi-region.

## Exit criteria
A client logs into their portal, sees a month of graded videos, downloads their billing report — and the numbers match `ai_runs` to the cent — while the nightly retention job keeps the S3 bill flat and a prompt A/B report shows which prompt version to promote.
