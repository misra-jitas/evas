# EVAS Web UI

Vite + React + TypeScript frontend for EVAS — a faithful port of the Claude Design
"instrument-panel" prototype. Three surfaces in one app, selected at login:

- **Reviewer Workbench** — Queue → keyboard-first Review screen (derived grade,
  three-state checklist, undo/autosave, instant submit→next, fading shortcut hints).
- **Ops Dashboard** — pipeline, discrepancy (prompt-tuning feed), throughput, cost,
  plus **Videos** and **Jobs**.
- **Sources** — register an S3/URL source, funnel bars, sync, detail.
- **AI Review** — agent observability: live pulse, aggregate strip (by model /
  prompt), runs log, run drill-down.
- **Client Portal** — read-only, tenancy-isolated (no cost/reviewer/model/confidence).

Design language: IBM Plex Sans + Mono, hairline grid, one cobalt accent, strict +
colorblind-safe status colors, light/dark via `[data-theme]`, EN/ES toggle.

## Develop

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173  (proxies /api -> http://localhost:8000)
```

Run the backend separately (`.venv/bin/python -m uvicorn evas.api.app:app`). The dev
server proxies `/api/*` to it, so no CORS setup is needed.

```bash
npm run typecheck      # tsc --noEmit
npm run build          # tsc + vite build -> dist/
```

## Live API vs mock

Screens fetch from the live FastAPI endpoints and **fall back to bundled mock
fixtures** when the backend is unreachable or returns nothing — so the UI always
renders, even against an empty DB. Currently wired live (with fallback):

| Screen | Endpoint |
|---|---|
| Sources list / sync | `GET /sources`, `POST /sources/{id}/sync` |
| AI Review runs / re-run | `GET /ai/runs`, `POST /ai/runs/{id}/rerun` |
| Dashboard pipeline "failed" | `GET /admin/metrics` |
| Client Portal list | `GET /portal/videos` |

Auth: role-based login mirrors the design. When `VITE_EVAS_BOOTSTRAP_TOKEN` is set
(see `.env.example`), login also mints a real JWT via `POST /auth/token`
(`X-Bootstrap-Token`) and attaches it as `Authorization: Bearer …` to API calls.

**Gaps that stay on mock** (no clean endpoint yet): the reviewer Queue + Review
interaction model (frame-level findings and human-review writes), Dashboard
discrepancy/throughput/cost tables, the Jobs list, and run drill-down frames.

## Serving in production

`npm run build` emits `dist/` (base path `/app/`). FastAPI auto-mounts it at
**`/app`** when present (`src/evas/api/app.py`), so the built UI is served from the
same origin as the API. Set `VITE_EVAS_API_BASE=/api` (default) accordingly, or point
it at an absolute API URL.
