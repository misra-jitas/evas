# EVAS — Milestone 2

Builds on Milestone 1 (ingestion → extraction → AI review → API). Same stack,
same **locked** `evas_schema.sql` — **no schema changes**; everything below is
already supported by existing tables/columns/enums.

## Scope

1. **Auth** — users, roles, route protection, per-client tenancy scoping.
2. **Human review** — assignments, grading, frame notes, AI-finding overrides, QA second pass.
3. **Webhook delivery** — the `notify` job, HMAC-signed deliveries with retries.
4. **Retention / archive** — the `purge_frames` and `archive` jobs + a sweep.

## 1. Auth

**Constraint:** the `users` table has **no password/credential column**, and the
schema is locked. So credentials are **not stored**. Auth is **stateless JWT**:

- Tokens are HS256 JWTs signed with `EVAS_JWT_SECRET`, claims `{sub: user_id,
  role, client_id, exp}`. No server-side session table.
- `POST /auth/token` mints a token for an existing **active** user by email. It
  is gated by an `X-Bootstrap-Token` header matching `EVAS_BOOTSTRAP_TOKEN`
  (interim bootstrap/dev mechanism). Real credential verification belongs to an
  external IdP and is **out of scope** here — this endpoint is the seam where
  that integration will plug in. Returns 503 if no bootstrap token is configured.
- `Authorization: Bearer <jwt>` is verified on protected routes via a
  `get_current_user` dependency (decodes, loads the user, rejects inactive).
- **Roles** (`user_role` enum): `admin`, `reviewer`, `client_viewer`.
  - `admin` — full access (create videos, manage webhooks, assign reviews, QA).
  - `reviewer` — internal; read all, perform human reviews, self-assign.
  - `client_viewer` — read-only, **scoped to their own `client_id`** (tenancy).
- Tenancy: `client_viewer` requests are filtered to their client; cross-client
  access → 404 (not 403, to avoid leaking existence).

New env: `EVAS_JWT_SECRET`, `EVAS_JWT_EXPIRE_MINUTES` (default 720),
`EVAS_BOOTSTRAP_TOKEN`.

## 2. Human review

Endpoints (reviewer/admin unless noted):

- `POST /videos/{id}/human-reviews` — assign a review (admin assigns to a
  reviewer; a reviewer may self-assign). Creates `human_reviews` (status
  `assigned`, references the video's active `checklist_id`). Audited.
- `GET /human-reviews?reviewer_id=&status=` — reviewer queue / listing.
- `GET /videos/{id}/human-reviews` — reviews for a video.
- `PATCH /human-reviews/{id}` — set `status` (in_progress/done), `grade`, `notes`.
  Grade change → `audit_log` `grade_changed`; transition to `done` sets
  `reviewed_at`. When a non-QA review reaches `done` with a grade, the video
  moves to `human_reviewed` (audited) and a `notify(video.human_reviewed)` job
  is enqueued.
- `PUT /human-reviews/{id}/frames/{frame_id}` — upsert `human_frame_notes`
  (`note`, `override_findings` — same JSON shape as AI findings).
- `POST /human-reviews/{id}/qa` — create a QA second-pass review
  (`is_qa_review = true`, `qa_of_review = {id}`).

## 3. Webhook delivery

- **Management** (admin): `POST /clients/{id}/webhooks`, `GET /clients/{id}/webhooks`,
  `DELETE /webhooks/{id}` (soft via `is_active=false`). `events` defaults to
  `{video.ai_reviewed, video.human_reviewed}`; `secret` is stored for HMAC.
- **`notify` job** (`job_type='notify'`, payload `{video_id, event}`): finds
  active endpoints for the video's client subscribed to `event`, and for each
  creates/ūpdates a `webhook_deliveries` row and POSTs the payload with header
  `X-EVAS-Signature: sha256=<hmac(secret, body)>` via `httpx`. Records
  `status_code`, `attempts`, `delivered_at`. **Idempotent**: deliveries already
  marked delivered (2xx) are skipped on retry; non-2xx raises so the job's
  normal retry/dead-letter logic applies.
- **Triggers**: AI review completion enqueues `notify(video.ai_reviewed)`;
  human-review completion enqueues `notify(video.human_reviewed)`.

## 4. Retention / archive

- **`purge_frames` job** (payload `{video_id}`): for the video, delete each
  non-purged frame's S3 image and set `frames.purged = true` (**keep the row**).
  Audited. Idempotent (skips already-purged frames).
- **`archive` job** (payload `{video_id}`): mark the source video archived —
  record `archived_at` in `videos.metadata` (jsonb) and audit. (No physical tier
  move in M2; the hook is here for an S3 lifecycle/Glacier step later.)
- **Sweep**: `evas retention-sweep` scans non-deleted clients with
  `frame_retention_days` / `video_archive_days` set and enqueues `purge_frames`
  / `archive` jobs for videos older than the threshold that aren't already
  purged/archived. Intended to run on a schedule (cron).

## Rules carried over (unchanged)

- Every status change → `audit_log` (`user_id` = acting user, or NULL = system).
- Never overwrite AI results; human overrides live in `human_frame_notes`.
- 12-factor config; no secrets in code. Soft deletes respect `deleted_at`.

## Out of scope (still deferred)

- Real credential storage / IdP integration (token endpoint is the seam).
- Clips / temporal review. Physical archive-tier movement.
