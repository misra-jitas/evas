# EVAS_SOURCES — Sources Screen & Source Registration

Audience: **Claude Design** (build the screen) and **Claude Code** (build the data + endpoints + sync). Sources is the **first nav item for admin** — it is where the pipeline begins. Everything downstream (frames, AI, review) starts with a source.

A **source** is a pointer to a place full of videos — an S3 bucket/prefix, or another enumerable URL. Registering a source lets EVAS scan it, discover videos, and enqueue ingest per file, so clients never register videos one at a time.

---

## A. Data model delta (Claude Code — propose migration, then merge into `evas_schema.sql`)

```sql
CREATE TYPE source_type   AS ENUM ('s3', 'url');          -- extend later: gdrive, gcs, azure
CREATE TYPE source_status AS ENUM ('connected', 'syncing', 'error', 'disabled');

CREATE TABLE sources (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id     uuid NOT NULL REFERENCES clients(id),
    label         text NOT NULL,                 -- "Halo — daily shift uploads"
    type          source_type NOT NULL,
    uri_prefix    text NOT NULL,                 -- s3://evas-videos/halo/  or  https://.../listing
    credential_ref text,                         -- name/ARN of secret, NEVER the secret itself
    sampling_override jsonb,                      -- applied to videos discovered here
    status        source_status NOT NULL DEFAULT 'connected',
    auto_sync     boolean NOT NULL DEFAULT false, -- re-scan on schedule
    last_synced_at timestamptz,
    last_error    text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at    timestamptz,
    UNIQUE (client_id, uri_prefix)
);

ALTER TABLE videos ADD COLUMN source_id uuid REFERENCES sources(id);  -- nullable; which source it came from
ALTER TYPE job_type ADD VALUE 'sync_source';                          -- enumerate a source, enqueue ingest per new video
```

Why a table and not derived-from-videos: a connected source with **zero videos yet** ("bucket wired up, nothing ingested") cannot be derived from the `videos` table. The table also holds credentials reference, sync schedule, and error state.

## B. Sync worker (Claude Code)

`sync_source` job:
1. Enumerate the source: S3 `ListObjectsV2` under `uri_prefix`, filter video extensions (.mp4/.mov/.mkv/...). For `url` type, fetch a listing/manifest and extract URIs.
2. For each discovered object → `POST /videos` register (existing flow), tagging `source_id`. Dedup by hash already prevents re-ingest.
3. Update `last_synced_at`; set `status=error` + `last_error` on failure (bad creds, prefix not found).
Idempotent: re-scan only enqueues genuinely new files. `auto_sync` sources scheduled nightly.

Endpoints: `POST /sources` (register), `POST /sources/{id}/sync` (scan now), `GET /sources` (list + funnel aggregates), `GET /sources/{id}` (detail + its videos), `PATCH /sources/{id}` (enable/disable, edit), `DELETE /sources/{id}` (soft).

## C. Sources screen (Claude Design) — admin, first nav item

### C.1 List view (`/sources`)
- Page header: "Sources" + primary button **"Register source"** (top-right).
- One card/row per source:
  - Left: type icon (S3 / link), **label**, `uri_prefix` in mono, client chip.
  - Status pill: connected (green) · syncing (animated) · error (red, shows `last_error` on hover) · disabled (grey).
  - **Funnel bar** — the heart of it: a single segmented progress bar showing `done / in-review / ingested / to-go` of total discovered, with counts: `142 total · 118 done · 11 in review · 8 queued · 5 to ingest`.
  - Right: `last_synced_at` (relative), **Sync now** button, kebab (edit / disable / delete).
- Empty state: "No sources connected. Register an S3 bucket or URL full of videos to begin." + the register button.

### C.2 Register source modal/flow
Fields:
- **Type** — segmented: S3 / URL (extensible).
- **URI / prefix** — `s3://bucket/prefix/` or `https://...`. Live validation hint.
- **Label** — human name.
- **Client** — select (which client owns these videos).
- **Credential** — dropdown of named credentials (never a raw secret field; "Manage credentials" link).
- **Sampling override** (optional, collapsed) — interval/max frames for videos from this source.
- **Auto-sync** toggle — re-scan nightly.
- Footer: **"Register & scan now"** (primary) / Cancel.
On submit → creates source, fires `sync_source`, returns to list showing the new source in `syncing` state with a live-incrementing discovered count.

### C.3 Source detail (`/sources/{id}`)
- Header: label, prefix, status, last sync, **Sync now**.
- Funnel as full stat row (total / ingested / in review / done / failed / to-go).
- Filtered video list (the `videos` view, scoped to this `source_id`) — reuses the Videos table component.
- Error panel if `status=error`: last_error + retry.

---

## Nav change (both)
Admin nav order becomes: **Sources · Dashboard · Videos · Jobs**. Sources first — it frames EVAS as "connect a source → watch it flow through."

## Out of scope (this doc)
Per-source webhooks · cross-client sources · non-enumerable single-file URLs (those still use the existing single `POST /videos`).
