// Shared data-model types for EVAS. These describe both the mock fixtures
// (src/data.ts) and the shapes the API layer normalizes into, so screens are
// agnostic to whether data came from the live backend or the local fallback.

export type Role = "reviewer" | "admin" | "client";
export type Priority = "rush" | "high" | "normal";
export type ItemState = "pending" | "confirmed" | "override-yes" | "override-no";

export interface Client {
  id: string;
  name: string;
  short: string;
  tint: string;
}

export interface Reviewer {
  id: string;
  name: string;
  initials: string;
}

export interface CurrentUser {
  id: string;
  name: string;
  initials: string;
  role: string;
}

export interface ChecklistItemDef {
  key: string;
  label: string;
  kind: string;
  expect: string;
  risk?: boolean;
}

export interface Checklist {
  name: string;
  version: string;
  grading_mode: string;
  items: ChecklistItemDef[];
}

export interface Scene {
  id: string;
  label: string;
  hue: number;
  act: string;
}

export interface FrameItem {
  key: string;
  label: string;
  expect: string;
  risk: boolean;
  aiValue: string;
  conf: number;
  state: ItemState;
}

export interface Frame {
  id: string;
  idx: number;
  t: number;
  timecode: string;
  scene: string;
  hue: number;
  flagged: boolean;
  touched: boolean;
  note: string;
  desc: string;
  items: FrameItem[];
}

export interface QueueItem {
  id: string;
  ref: string;
  client: Client;
  scene: string;
  sceneLabel: string;
  priority: Priority;
  aiGrade: number;
  frameCount: number;
  flaggedCount: number;
  flaggedIdx: number[];
  duration: string;
  assignedMins: number;
  model: string;
  promptVersion: string;
  checklist: Checklist;
  aiSummary: string;
}

export type Review = QueueItem & { frames: Frame[] };

export type SourceStatus = "connected" | "syncing" | "error" | "disabled";

export interface Source {
  id: string;
  type: "s3" | "url";
  label: string;
  uri: string;
  cred: string;
  client: string;
  clientObj: Client;
  status: SourceStatus;
  autoSync: boolean;
  lastSync: number;
  lastError?: string;
  total: number;
  done: number;
  inReview: number;
  ingested: number;
  toGo: number;
  failed: number;
}

export type RunStatus = "queued" | "running" | "completed" | "failed";

export interface AiRun {
  id: string;
  ref: string;
  client: string;
  clientObj: Client;
  sceneLabel: string;
  scene: string;
  model: string;
  prompt: string;
  status: RunStatus;
  done: number;
  total: number;
  grade: number | null;
  flagged: number;
  tokIn: number;
  tokOut: number;
  tokens: number;
  cost: number;
  dur: number | null;
  started: number;
  error?: string;
}

export type AiRunDetail = AiRun & { frames: Frame[]; allCount: number };

export interface SparkSet {
  videosHr: number[];
  costVideo: number[];
  conf: number[];
  flagged: number[];
  err: number[];
}

export interface AiStatGroup {
  key: string;
  videosHr: number;
  costVideo: number;
  avgConf: number;
  flaggedRate: number;
  errRate: number;
  spark: SparkSet;
}

export interface AiStats {
  byModel: AiStatGroup[];
  byPrompt: AiStatGroup[];
}

export interface PipelineStage {
  key: string;
  label: string;
  count: number;
  tone: string;
}

export interface Discrepancy {
  ref: string;
  client: Client;
  ai: number;
  human: number;
  model: string;
  prompt: string;
  gap: number;
}

export interface Throughput {
  r: string;
  reviewer: Reviewer;
  perDay: number;
  avgMin: number;
  overrideRate: number;
  qaAgree: number;
}

export interface CostRow {
  client: string;
  clientObj: Client;
  videos: number;
  frames: number;
  tokens: number;
  cost: number;
  trend: number[];
}

export interface Job {
  id: string;
  ref: string;
  stage: string;
  status: "failed" | "dead" | "running";
  attempts: number;
  lastError: string;
  client: string;
  clientObj: Client;
  at: string;
}

export interface PortalVideo {
  ref: string;
  uploaded: string;
  status: "reviewed" | "in_review" | "processing";
  grade: number | null;
  scene: string;
}

export type Lang = "en" | "es";
export type Theme = "light" | "dark";
export type TFn = (k: string) => string;
