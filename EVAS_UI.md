# EVAS_UI — Interface Specification

Three surfaces, one design system. Stack: small React app (Vite), Tailwind, server data via the FastAPI endpoints. Keep it light — no heavy state library; React Query for data, URL as state where possible. Bilingual-ready (ES/EN): all strings in a translation file from day one.

Build order: Reviewer Workbench (M2) → Ops Dashboard (M2) → Client Portal (M3).

---

## 1. Reviewer Workbench (M2) — the money screen

A reviewer clears 30–50 videos/day. Every click and every second here multiplies. Optimize for keyboard-first flow.

### 1.1 Queue screen (`/queue`)
- List of assigned reviews: thumbnail, external_ref, client, priority badge, AI grade, frame count, flagged-frame count, assigned_at.
- Sort: priority desc, then assigned_at asc. Rush items visually loud (red badge).
- One primary action: **"Start next"** button (top, large) → opens the oldest highest-priority review. Reviewers should not browse; they should flow.

### 1.2 Review screen (`/review/:id`) — split layout
**Left rail (20%)** — video context:
- Video player of the source (seek syncs to selected frame's timecode; selecting a frame seeks the player).
- Metadata: client, external_ref, duration, checklist name+version, AI grade + summary.

**Center (60%)** — frame strip + detail:
- Horizontal filmstrip of frame thumbnails with timecode labels. Flagged (low-confidence) frames get an amber dot and **sort-first toggle** (default ON: flagged first, then chronological).
- Selected frame large in center. AI description below it.
- Checklist panel: one row per item — label, AI value, AI confidence bar, and a three-state control: **Confirm / Override-Yes / Override-No**. Confirmed rows collapse visually; overridden rows highlight.
- Frame note: single text field, autosaves on blur.

**Right rail (20%)** — verdict:
- Running tally: frames reviewed / total, overrides count.
- Video grade input (0–10, step 0.5) — if checklist `grading_mode = derived`, show the computed grade as default, editable.
- Video notes textarea.
- **Submit review** (disabled until all flagged frames touched).

### 1.3 Keyboard shortcuts (non-negotiable)
| Key | Action |
|---|---|
| `→` / `←` | next / previous frame |
| `f` | next flagged frame |
| `1..9`, `0` | jump to checklist item 1–10 |
| `c` | confirm current item |
| `y` / `n` | override yes / no |
| `a` | **confirm all AI findings on current frame** |
| `Shift+A` | confirm all remaining unflagged frames (with confirm dialog) |
| `g` | focus grade input |
| `Enter` (in grade) | submit review |

`a` and `Shift+A` are the throughput features: when AI is right (most of the time), a frame costs one keystroke.

### 1.4 QA review mode
Same screen, banner: "QA review of [reviewer name]". Shows the original reviewer's findings alongside AI's; QA confirms/overrides against both. Agreement % shown on submit.

---

## 2. Ops Dashboard (M2) — `/dashboard` (admin only)

Single page, four blocks. Data straight from `video_review_board` + aggregates. Filters: client, date range.

1. **Pipeline status** — count cards per video status (ingested → done), failed in red, click → filtered video list.
2. **Discrepancy table** — videos where |ai_grade − human_grade| ≥ threshold (configurable, default 2). Columns: video, client, AI grade, human grade, gap, model, prompt_version. This is the prompt-tuning feed.
3. **Reviewer throughput** — per reviewer: reviews/day, avg minutes/video, override rate, QA agreement %.
4. **Cost** — per client: videos, frames, tokens, cost_usd (month to date), cost per video trend.

Plus `/videos` (admin list with search/filters, links into a read-only version of the review screen) and `/jobs` (processing_jobs table: failed/dead jobs with last_error, retry button).

---

## 3. Client Portal (M3) — `/portal`

Read-only, tenancy-isolated (client_viewer sees only their client_id — enforced server-side, tested).

- **Videos list** — external_ref, uploaded_at, status (simplified to: Processing / In review / Reviewed), final grade.
- **Video detail** — grade, summary, checklist results (final = human override where present, else AI), notable frames with notes. No internal data: no costs, no reviewer names, no model/prompt info, no confidence scores.
- **Exports** — CSV of findings per date range; monthly billing report download (M3 billing feature).
- Branding: client name/logo top-left, neutral EVAS styling.

---

## Shared

- **Design language**: clean, dense, desktop-first (reviewers work on monitors). Dark mode optional, later.
- **States**: every list has empty/loading/error states designed, not improvised.
- **Auth**: login screen, JWT, role-based routing (reviewer → /queue, admin → /dashboard, client_viewer → /portal).
- **i18n**: ES/EN toggle in user menu; default by user preference field.
- **Audit hooks**: every grade change / override fires the existing audit endpoints — UI never writes silently.

## Out of scope (M4+)
Client self-upload UI · mobile layouts · annotation drawing on frames (boxes/polygons — if needed, integrate Label Studio rather than rebuilding it) · realtime collaboration.
