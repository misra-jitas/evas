# EVAS_AI_MONITOR — AI Review Observability Screen

Audience: **Claude Design** (build the screen) and **Claude Code** (wire the data). New **admin** nav item: **AI Review**. Jobs shows mechanical job status; this screen shows the *agent's actual work* — what it reviewed, what it found, where it struggled. No schema change needed: all data already lives in `ai_runs`, `ai_frame_findings`, and `processing_jobs` (type `ai_review`).

---

## A. Data (Claude Code)

Endpoints (read-only):
- `GET /ai/runs` — list runs: filters by status, client, model, prompt_version, date. Returns video ref, model, prompt_version, status, frames done/total, grade, tokens, cost, duration, error.
- `GET /ai/runs/{id}` — drill-down: per-frame findings (description, values, confidence, flagged), token/cost breakdown, timeline.
- `GET /ai/stats` — aggregates over a date range: throughput (videos/hr), avg cost/video, avg confidence, flagged-frame rate, error rate, grouped by model & prompt_version.

## B. AI Review screen (Claude Design) — admin

### B.1 Header band — live pulse
Four stat cards, auto-refresh:
- **In progress** — runs currently `running` (animated), e.g. "3 running · 1,240 frames".
- **Queued** — `ai_review` jobs waiting.
- **Done today** — completed runs + videos graded.
- **Issues** — failed runs + dead `ai_review` jobs (red if > 0, click → filtered).

### B.2 Aggregate strip (from `GET /ai/stats`)
Compact row: throughput (videos/hr) · avg cost/video · avg confidence · flagged-frame rate · error rate. Each with a small sparkline over the selected range. Group-by toggle: **by model** / **by prompt_version** — so you can see "prompt v2.3 is cheaper but flags more."

### B.3 Runs table — the work log
One row per `ai_run`, newest first. Columns:
- Video ref + client chip
- Model + prompt_version (mono)
- Status pill (queued / running / completed / failed) — running shows `frames 84/120` progress
- Grade output (or — if not done)
- Flagged frames count (amber if high)
- Tokens · cost
- Duration
- Started (relative)
Row click → drill-down. Failed rows show error inline, with a **Re-run** action (creates a new run, never overwrites — history preserved).

Filters: status, client, model, prompt_version, date range, "has issues" toggle.

### B.4 Run drill-down (`/ai/runs/{id}`)
- Top: video context, model, prompt_version, total tokens/cost/duration, final grade + summary.
- **Frame timeline** — horizontal strip; each frame marked by confidence (green→amber→red); flagged frames stand out. Click a frame → its AI description + per-checklist-item values & confidence (the raw of what the agent "said").
- **Issues panel** — frames below confidence threshold, any parse/validation errors, retries.
- **Cost breakdown** — tokens in/out, $ per frame.
- Cross-link: if a human review exists, show AI vs human grade gap and link to the discrepancy view (ties into the dashboard).

---

## Why this screen earns its place
- **Trust** — you can see exactly what the agent did per video, not just "ai_reviewed = true".
- **Tuning feed** — flagged rate + confidence by prompt_version tells you which prompt to promote (feeds the M3 prompt A/B).
- **Cost control** — cost/video trend by model surfaces spend before the bill does.
- **Debugging** — a bad grade traces to the exact frame and the exact thing the model said about it.

## Nav (both)
Admin nav becomes: **Sources · Dashboard · Videos · AI Review · Jobs**.

## Out of scope
Editing AI output here (corrections happen in the human review workbench) · prompt editing UI (M3 tool).
