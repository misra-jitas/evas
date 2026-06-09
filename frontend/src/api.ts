// EVAS API client — typed fetch wrapper with JWT, plus adapters that normalize
// live FastAPI responses into the prototype's data shapes. Screens call the
// `useLive` hook, which returns live data when the backend answers and falls
// back to the local mock fixtures (src/data.ts) otherwise, so the UI always
// renders against an empty or unauthenticated backend during development.
import { useEffect, useState } from "react";
import { D, sceneOf } from "./data";
import type { AiRunDetail, AiStatGroup, AiStats, BoardVideo, AiRun, Client, Frame, FrameItem, PortalVideo, Source } from "./types";

const BASE: string = (import.meta.env.VITE_EVAS_API_BASE as string) || "/api";
const BOOTSTRAP: string = (import.meta.env.VITE_EVAS_BOOTSTRAP_TOKEN as string) || "";

/** True when a bootstrap token is configured, so live login can be attempted. */
export const BOOTSTRAP_CONFIGURED: boolean = !!BOOTSTRAP;

const TOKEN_KEY = "evas-jwt";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(tok: string | null): void {
  if (tok) localStorage.setItem(TOKEN_KEY, tok);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  const tok = getToken();
  if (tok) headers.set("Authorization", `Bearer ${tok}`);
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText}`);
  const ct = res.headers.get("content-type") || "";
  return (ct.includes("json") ? await res.json() : await res.text()) as T;
}

/** Mint a JWT via the bootstrap mechanism. Requires VITE_EVAS_BOOTSTRAP_TOKEN. */
export async function login(email: string): Promise<string> {
  const body = JSON.stringify({ email });
  const res = await fetch(`${BASE}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Bootstrap-Token": BOOTSTRAP },
    body,
  });
  if (!res.ok) throw new ApiError(res.status, "token request failed");
  const data = (await res.json()) as { access_token: string };
  setToken(data.access_token);
  return data.access_token;
}

export function isLiveConfigured(): boolean {
  return BASE !== "/api" || !!getToken() || !!BOOTSTRAP;
}

// ---- deterministic visuals for live records the API doesn't carry ----
function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) & 0x7fffffff;
  return h;
}
const TINTS = D.CLIENTS.map((c) => c.tint);
export function tintFor(id: string): string {
  return TINTS[hash(id) % TINTS.length];
}
export function sceneFor(id: string): string {
  return D.SCENES[hash(id) % D.SCENES.length].id;
}
function clientFromId(id: string, name?: string): Client {
  const short = (name || id).replace(/[^A-Za-z]/g, "").slice(0, 4).toUpperCase() || "EVAS";
  return { id, name: name || id, short, tint: tintFor(id) };
}

// ---- raw response types (subset of fields we consume) ----
interface RawSource {
  id: string;
  client_id: string;
  label: string;
  type: "s3" | "url";
  uri_prefix: string;
  credential_ref: string | null;
  status: Source["status"];
  auto_sync: boolean;
  last_synced_at: string | null;
  last_error: string | null;
  funnel: { total: number; to_ingest: number; ingested: number; in_review: number; done: number; failed: number };
}
interface RawRun {
  id: string;
  video_id: string;
  external_ref: string | null;
  client_id: string;
  model: string;
  prompt_version: string;
  status: AiRun["status"];
  grade: number | null;
  frames_done: number;
  frames_total: number;
  flagged_frames: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  duration_seconds: number | null;
  error: string | null;
  started_at: string | null;
}
interface RawPortalVideo {
  id: string;
  external_ref: string | null;
  uploaded_at: string;
  status: string;
  final_grade: number | null;
}

function minutesAgo(iso: string | null): number {
  if (!iso) return 0;
  return Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
}

// ---- adapters: raw -> prototype shape ----
function adaptSource(r: RawSource): Source {
  const f = r.funnel;
  return {
    id: r.id,
    type: r.type,
    label: r.label,
    uri: r.uri_prefix,
    cred: r.credential_ref || "",
    client: r.client_id,
    clientObj: clientFromId(r.client_id),
    status: r.status,
    autoSync: r.auto_sync,
    lastSync: minutesAgo(r.last_synced_at),
    lastError: r.last_error || undefined,
    total: f.total,
    done: f.done,
    inReview: f.in_review,
    ingested: f.ingested,
    toGo: f.to_ingest,
    failed: f.failed,
  };
}
function adaptRun(r: RawRun): AiRun {
  return {
    id: r.id,
    ref: r.external_ref || r.video_id.slice(0, 8),
    client: r.client_id,
    clientObj: clientFromId(r.client_id),
    scene: sceneFor(r.video_id),
    sceneLabel: sceneOf(sceneFor(r.video_id)).label,
    model: r.model,
    prompt: r.prompt_version,
    status: r.status,
    done: r.frames_done,
    total: r.frames_total || r.frames_done,
    grade: r.grade,
    flagged: r.flagged_frames,
    tokIn: r.tokens_in,
    tokOut: r.tokens_out,
    tokens: r.tokens_in + r.tokens_out,
    cost: r.cost_usd,
    dur: r.duration_seconds,
    started: minutesAgo(r.started_at),
    error: r.error || undefined,
  };
}
const PORTAL_STATUS: Record<string, PortalVideo["status"]> = {
  Reviewed: "reviewed",
  "In review": "in_review",
  Processing: "processing",
  Failed: "processing",
};
function adaptPortalVideo(r: RawPortalVideo): PortalVideo {
  return {
    ref: r.external_ref || r.id.slice(0, 8),
    uploaded: r.uploaded_at.slice(0, 10),
    status: PORTAL_STATUS[r.status] || "processing",
    grade: r.final_grade,
    scene: sceneFor(r.id),
  };
}

// ---- board videos (GET /videos) ----
interface RawBoard {
  id: string;
  client_id: string;
  external_ref: string | null;
  status: string;
  priority: string;
  ai_grade: number | null;
  ai_model: string | null;
  human_grade: number | null;
  grade_discrepancy: number | null;
  uploaded_at: string;
  source_id: string | null;
}
function adaptBoard(r: RawBoard): BoardVideo {
  return {
    id: r.id,
    ref: r.external_ref || r.id.slice(0, 8),
    clientId: r.client_id,
    clientObj: clientFromId(r.client_id),
    status: r.status,
    priority: r.priority,
    aiGrade: r.ai_grade,
    aiModel: r.ai_model,
    humanGrade: r.human_grade,
    gap: r.grade_discrepancy,
    scene: sceneFor(r.id),
    uploaded: r.uploaded_at.slice(0, 10),
  };
}

// ---- AI stats (GET /ai/stats) ----
interface RawStatGroup {
  key: string;
  throughput_per_hour: number;
  avg_cost_usd: number;
  avg_confidence: number | null;
  flagged_rate: number;
  error_rate: number;
}
interface RawStats {
  by_model: RawStatGroup[];
  by_prompt_version: RawStatGroup[];
}
const flat = (v: number): number[] => [v, v];
function adaptStatGroup(g: RawStatGroup): AiStatGroup {
  const conf = g.avg_confidence ?? 0;
  return {
    key: g.key,
    videosHr: g.throughput_per_hour,
    costVideo: g.avg_cost_usd,
    avgConf: conf,
    flaggedRate: g.flagged_rate,
    errRate: g.error_rate,
    // The live endpoint has no time series, so sparklines render flat (honest).
    spark: { videosHr: flat(g.throughput_per_hour), costVideo: flat(g.avg_cost_usd), conf: flat(conf), flagged: flat(g.flagged_rate), err: flat(g.error_rate) },
  };
}
function adaptStats(r: RawStats): AiStats {
  return { byModel: r.by_model.map(adaptStatGroup), byPrompt: r.by_prompt_version.map(adaptStatGroup) };
}

// ---- run drill-down (GET /ai/runs/{id}) ----
interface RawDetailFrame {
  frame_index: number;
  timecode_label: string;
  timecode_seconds: number;
  description: string | null;
  findings: Record<string, { value: unknown; confidence: number | null }>;
  flagged: boolean;
}
interface RawRunDetail {
  id: string;
  video_id: string;
  external_ref: string | null;
  client_id: string;
  model: string;
  prompt_version: string;
  status: AiRun["status"];
  grade: number | null;
  error: string | null;
  duration_seconds: number | null;
  cost: { tokens_in: number; tokens_out: number; cost_usd: number; cost_per_frame: number | null };
  issues: { flagged_count: number };
  frames: RawDetailFrame[];
}
const yesNo = (v: unknown): string => (v === true || v === "Yes" || v === "yes" ? "Yes" : "No");
function adaptRunDetail(r: RawRunDetail): AiRunDetail {
  const scene = sceneFor(r.video_id);
  const frames: Frame[] = r.frames.map((f) => {
    const items: FrameItem[] = Object.entries(f.findings || {}).map(([key, val]) => ({
      key,
      label: key,
      expect: "",
      risk: false,
      aiValue: yesNo(val?.value),
      conf: val?.confidence ?? 0,
      state: "pending",
    }));
    return { id: `fr-${f.frame_index}`, idx: f.frame_index, t: f.timecode_seconds, timecode: f.timecode_label, scene, hue: sceneOf(scene).hue, flagged: f.flagged, touched: false, note: "", desc: f.description || "", items };
  });
  return {
    id: r.id,
    ref: r.external_ref || r.video_id.slice(0, 8),
    client: r.client_id,
    clientObj: clientFromId(r.client_id),
    scene,
    sceneLabel: sceneOf(scene).label,
    model: r.model,
    prompt: r.prompt_version,
    status: r.status,
    done: frames.length,
    total: frames.length,
    grade: r.grade,
    flagged: r.issues?.flagged_count ?? 0,
    tokIn: r.cost.tokens_in,
    tokOut: r.cost.tokens_out,
    tokens: r.cost.tokens_in + r.cost.tokens_out,
    cost: r.cost.cost_usd,
    dur: r.duration_seconds,
    started: 0,
    error: r.error || undefined,
    frames,
    allCount: frames.length,
  };
}

export interface ClientRecord {
  id: string;
  name: string;
  slug: string;
  sampling_config: Record<string, unknown>;
  frame_retention_days: number | null;
  video_archive_days: number | null;
  video_count: number;
}
export interface ClientInput {
  name: string;
  slug: string;
  sampling_config?: Record<string, unknown>;
  frame_retention_days?: number | null;
  video_archive_days?: number | null;
}

function jsonInit(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

// ---- typed endpoint calls ----
export const api = {
  listClients: () => request<ClientRecord[]>("/clients"),
  createClient: (body: ClientInput) => request<ClientRecord>("/clients", jsonInit("POST", body)),
  updateClient: (id: string, body: Partial<ClientInput>) =>
    request<ClientRecord>(`/clients/${id}`, jsonInit("PATCH", body)),
  deleteClient: (id: string) => request(`/clients/${id}`, { method: "DELETE" }),
  listSources: () => request<RawSource[]>("/sources").then((rows) => rows.map(adaptSource)),
  createSource: (body: {
    client_id: string;
    label: string;
    type: "s3" | "url";
    uri_prefix: string;
    credential_ref?: string | null;
    auto_sync?: boolean;
  }) => request<RawSource>("/sources", jsonInit("POST", body)).then(adaptSource),
  syncSource: (id: string) => request(`/sources/${id}/sync`, { method: "POST" }),
  listRuns: (qs = "") => request<RawRun[]>(`/ai/runs${qs}`).then((rows) => rows.map(adaptRun)),
  runStats: () => request<RawStats>("/ai/stats").then(adaptStats),
  runDetail: (id: string) => request<RawRunDetail>(`/ai/runs/${id}`).then(adaptRunDetail),
  boardVideos: () => request<RawBoard[]>("/videos").then((rows) => rows.map(adaptBoard)),
  rerun: (id: string) => request(`/ai/runs/${id}/rerun`, { method: "POST" }),
  adminMetrics: () =>
    request<{ dead_jobs: number; queue_depth: number; running_jobs: number; webhook_failures: number }>(
      "/admin/metrics",
    ),
  portalVideos: () =>
    request<RawPortalVideo[]>("/portal/videos").then((rows) => rows.map(adaptPortalVideo)),
};

export interface Live<T> {
  data: T;
  loading: boolean;
  live: boolean;
  error: string | null;
  reload: () => void;
}

/**
 * Fetch live data with a typed fallback. `fetcher` hits the API; if it throws
 * (network/auth/404) or returns an empty array, `fallback` (mock) is used and
 * `live` is false so screens can badge the data source if desired.
 */
export function useLive<T>(fetcher: () => Promise<T>, fallback: T, deps: unknown[] = []): Live<T> {
  const [state, setState] = useState<Omit<Live<T>, "reload">>({
    data: fallback,
    loading: true,
    live: false,
    error: null,
  });
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true }));
    fetcher()
      .then((data) => {
        if (!alive) return;
        const empty = Array.isArray(data) && data.length === 0;
        if (empty) setState({ data: fallback, loading: false, live: false, error: null });
        else setState({ data, loading: false, live: true, error: null });
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setState({ data: fallback, loading: false, live: false, error: String(e) });
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonce, ...deps]);
  return { ...state, reload: () => setNonce((n) => n + 1) };
}
