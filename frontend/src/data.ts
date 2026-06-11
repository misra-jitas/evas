// EVAS mock data layer (egocentric video QA), ported from the design prototype.
// Used as the offline fallback when the live API is unreachable/empty, and as
// the source of scene/checklist visuals (POV gradients, descriptions) that the
// backend doesn't carry.
import type {
  AiRun,
  AiRunDetail,
  AiStats,
  Checklist,
  Client,
  CostRow,
  CurrentUser,
  Discrepancy,
  Frame,
  FrameItem,
  Job,
  PipelineStage,
  PortalVideo,
  QueueItem,
  Review,
  Reviewer,
  Scene,
  Source,
  Throughput,
} from "./types";

const CLIENTS: Client[] = [
  { id: "halo", name: "Halo Robotics", short: "HALO", tint: "oklch(0.55 0.17 252)" },
  { id: "meridian", name: "Meridian Labs", short: "MRDN", tint: "oklch(0.55 0.15 162)" },
  { id: "okta-v", name: "Okta Vision", short: "OKTA", tint: "oklch(0.55 0.18 300)" },
  { id: "northwind", name: "Northwind AI", short: "NRTH", tint: "oklch(0.6 0.16 50)" },
  { id: "cobalt", name: "Cobalt Embodied", short: "CBLT", tint: "oklch(0.55 0.16 232)" },
];

const REVIEWERS: Reviewer[] = [
  { id: "r-elena", name: "Elena Park", initials: "EP" },
  { id: "r-marco", name: "Marco Díaz", initials: "MD" },
  { id: "r-sana", name: "Sana Okafor", initials: "SO" },
  { id: "r-theo", name: "Theo Lindqvist", initials: "TL" },
  { id: "r-yuki", name: "Yuki Tanaka", initials: "YT" },
];

const CURRENT: CurrentUser = { id: "r-elena", name: "Elena Park", initials: "EP", role: "reviewer" };

const CHECKLIST: Checklist = {
  name: "Egocentric QA",
  version: "v4.2",
  grading_mode: "derived",
  items: [
    { key: "hands", label: "Wearer hands visible", kind: "bool", expect: "Yes" },
    { key: "activity", label: "Primary activity identifiable", kind: "bool", expect: "Yes" },
    { key: "faces", label: "Bystander face(s) — PII", kind: "bool", expect: "No", risk: true },
    { key: "plates", label: "Plates / screen text — PII", kind: "bool", expect: "No", risk: true },
    { key: "blur", label: "Severe motion blur", kind: "bool", expect: "No" },
    { key: "occluded", label: "Lens occluded / fingered", kind: "bool", expect: "No" },
    { key: "object", label: "Object-of-interaction in frame", kind: "bool", expect: "Yes" },
    { key: "label", label: "Activity label matches", kind: "bool", expect: "Yes" },
  ],
};

const SCENES: Scene[] = [
  { id: "kitchen", label: "KITCHEN", hue: 42, act: "Preparing pour-over coffee" },
  { id: "street", label: "STREET", hue: 232, act: "Crossing a residential street" },
  { id: "desk", label: "WORKSPACE", hue: 265, act: "Assembling a mechanical keyboard" },
  { id: "garage", label: "GARAGE", hue: 28, act: "Changing a bicycle tire" },
  { id: "market", label: "MARKET", hue: 152, act: "Selecting produce at a stall" },
  { id: "lab", label: "LAB", hue: 200, act: "Pipetting into a 96-well plate" },
];

const DESCRIPTIONS: Record<string, string[]> = {
  kitchen: [
    "Wearer's right hand grips a gooseneck kettle; steam rising over a ceramic dripper on the counter.",
    "Both hands fold a paper filter into the V60; bag of beans visible at frame left.",
    "Pouring water in slow spiral; bloom forming in the coffee bed, hands steady at center.",
    "Reaching across to a mug; reflective toaster surface at right shows a partial face.",
  ],
  street: [
    "Wearer steps off a curb; parked sedan license plate legible in lower-left quadrant.",
    "Mid-crossing, looking left toward oncoming cyclist; hands not in frame.",
    "Approaching far sidewalk; a pedestrian's face is clearly visible 3m ahead.",
    "Heavy camera shake during a quick head-turn; scene smeared, low detail.",
  ],
  desk: [
    "Wearer seats a switch into the PCB; tweezers held in right hand, parts tray at left.",
    "Close inspection of stabilizers; monitor in background displays readable email text.",
    "Both hands flexing a keyboard plate; soldering iron resting on stand at frame edge.",
    "Lens partially covered by a thumb; lower third of frame is dark and blurred.",
  ],
  garage: [
    "Wearer pries the tire bead with levers; greasy hands centered over the wheel.",
    "Inflating the inner tube; pressure gauge needle readable at center.",
    "Reaching for a wrench on the pegboard; no hands in frame during the reach.",
    "Wheel reseated on the frame; workshop radio screen shows a station name.",
  ],
  market: [
    "Wearer's hand weighs a tomato; vendor's face visible across the stall.",
    "Scanning crates of citrus; price chalkboard text fully legible.",
    "Bagging apples, both hands working; background crowd softly out of focus.",
    "Quick pan to the next stall; motion blur across the whole frame.",
  ],
  lab: [
    "Gloved hands operate a multichannel pipette over a 96-well plate.",
    "Adjusting the micropipette volume dial; reading clearly shows 200 µL.",
    "Reagent reservoir at center; sample-rack barcode readable at frame right.",
    "Bench monitor in background displays an unredacted patient ID string.",
  ],
};

let SEED = 91;
function rnd(): number {
  SEED = (SEED * 1103515245 + 12345) & 0x7fffffff;
  return SEED / 0x7fffffff;
}

export function tc(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  const f = Math.floor((sec % 1) * 30);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}:${String(f).padStart(2, "0")}`;
}

function buildFrames(sceneId: string, count: number, flaggedIdx: number[]): Frame[] {
  const desc = DESCRIPTIONS[sceneId];
  const frames: Frame[] = [];
  let t = 0;
  for (let i = 0; i < count; i++) {
    t += 1.6 + rnd() * 2.4;
    const isFlag = flaggedIdx.includes(i);
    const items: FrameItem[] = CHECKLIST.items.map((def) => {
      let value = def.expect;
      let conf = 0.86 + rnd() * 0.13;
      if (isFlag) {
        if (def.risk && rnd() > 0.45) {
          value = def.expect === "No" ? "Yes" : "No";
          conf = 0.41 + rnd() * 0.18;
        }
        if (def.key === "blur" && rnd() > 0.6) {
          value = "Yes";
          conf = 0.44 + rnd() * 0.2;
        }
        if (def.key === "hands" && rnd() > 0.7) {
          value = "No";
          conf = 0.48 + rnd() * 0.15;
        }
      } else if (rnd() > 0.9) {
        conf = 0.62 + rnd() * 0.12;
      }
      return {
        key: def.key,
        label: def.label,
        expect: def.expect,
        risk: !!def.risk,
        aiValue: value,
        conf: Math.round(conf * 100) / 100,
        state: "pending" as const,
      };
    });
    const scene = SCENES.find((s) => s.id === sceneId)!;
    frames.push({
      id: `fr-${i}`,
      idx: i,
      t: Math.round(t * 100) / 100,
      timecode: tc(t),
      scene: sceneId,
      hue: scene.hue + (rnd() * 16 - 8),
      flagged: isFlag,
      touched: false,
      note: "",
      desc: desc[i % desc.length],
      items,
    });
  }
  return frames;
}

function clientOf(id: string): Client {
  return CLIENTS.find((c) => c.id === id) ?? CLIENTS[0];
}

function aiSummaryFor(scene: string, grade: number, flags: number): string {
  const s = SCENES.find((x) => x.id === scene)!;
  const q =
    grade >= 8
      ? "High-quality clip, activity clearly framed throughout."
      : grade >= 6
        ? "Usable clip with intermittent quality dips."
        : "Marginal clip — multiple frames need human judgement.";
  return `${s.act}. ${q} ${flags} frame${flags === 1 ? "" : "s"} flagged for low confidence (PII / blur).`;
}

const QUEUE_DEF = [
  { ref: "EGO-24817", client: "halo", scene: "street", priority: "rush", ai: 4.5, frames: 32, flagged: [2, 5, 9, 17, 24], mins: 12 },
  { ref: "EGO-24820", client: "cobalt", scene: "lab", priority: "rush", ai: 6.0, frames: 28, flagged: [3, 11, 19], mins: 21 },
  { ref: "EGO-24799", client: "meridian", scene: "kitchen", priority: "high", ai: 8.5, frames: 24, flagged: [7, 15], mins: 34 },
  { ref: "EGO-24802", client: "northwind", scene: "garage", priority: "high", ai: 7.0, frames: 30, flagged: [4, 12, 22], mins: 41 },
  { ref: "EGO-24788", client: "okta-v", scene: "desk", priority: "normal", ai: 9.0, frames: 22, flagged: [9], mins: 58 },
  { ref: "EGO-24791", client: "halo", scene: "market", priority: "normal", ai: 7.5, frames: 26, flagged: [6, 18], mins: 73 },
  { ref: "EGO-24776", client: "meridian", scene: "kitchen", priority: "normal", ai: 8.0, frames: 20, flagged: [11], mins: 96 },
] as const;

const QUEUE: QueueItem[] = QUEUE_DEF.map((q) => {
  const c = clientOf(q.client);
  return {
    id: q.ref,
    ref: q.ref,
    client: c,
    scene: q.scene,
    sceneLabel: SCENES.find((s) => s.id === q.scene)!.label,
    priority: q.priority,
    aiGrade: q.ai,
    frameCount: q.frames,
    flaggedCount: q.flagged.length,
    flaggedIdx: [...q.flagged],
    duration: tc(q.frames * 2.4),
    assignedMins: q.mins,
    model: "evas-vlm-3",
    promptVersion: "p-118",
    checklist: CHECKLIST,
    aiSummary: aiSummaryFor(q.scene, q.ai, q.flagged.length),
  };
});

function getReview(id: string): Review {
  const q = QUEUE.find((x) => x.id === id) ?? QUEUE[0];
  SEED = 91 + parseInt(q.ref.slice(-3), 10);
  const frames = buildFrames(q.scene, q.frameCount, q.flaggedIdx);
  return { ...q, frames };
}

const PIPELINE: PipelineStage[] = [
  { key: "ingested", label: "Ingested", count: 41, tone: "ink" },
  { key: "extracted", label: "Frames out", count: 38, tone: "ink" },
  { key: "ai_graded", label: "AI graded", count: 33, tone: "accent" },
  { key: "in_review", label: "In review", count: 19, tone: "amber" },
  { key: "done", label: "Done", count: 214, tone: "green" },
  { key: "failed", label: "Failed", count: 3, tone: "red" },
];

const DISCREPANCY: Discrepancy[] = (
  [
    { ref: "EGO-24640", client: "halo", ai: 8.5, human: 4.5, model: "evas-vlm-3", prompt: "p-118" },
    { ref: "EGO-24655", client: "cobalt", ai: 3.0, human: 6.5, model: "evas-vlm-3", prompt: "p-118" },
    { ref: "EGO-24661", client: "meridian", ai: 9.0, human: 6.0, model: "evas-vlm-3", prompt: "p-117" },
    { ref: "EGO-24672", client: "okta-v", ai: 5.5, human: 9.0, model: "evas-vlm-3", prompt: "p-118" },
    { ref: "EGO-24690", client: "northwind", ai: 7.5, human: 4.0, model: "evas-vlm-2", prompt: "p-116" },
    { ref: "EGO-24701", client: "halo", ai: 2.5, human: 5.5, model: "evas-vlm-3", prompt: "p-118" },
  ] as const
).map((d) => ({ ...d, client: clientOf(d.client), gap: Math.round(Math.abs(d.ai - d.human) * 10) / 10 }));

const THROUGHPUT: Throughput[] = (
  [
    { r: "r-elena", perDay: 47, avgMin: 9.2, overrideRate: 0.14, qaAgree: 0.96 },
    { r: "r-marco", perDay: 38, avgMin: 11.8, overrideRate: 0.21, qaAgree: 0.91 },
    { r: "r-sana", perDay: 52, avgMin: 7.9, overrideRate: 0.11, qaAgree: 0.98 },
    { r: "r-theo", perDay: 29, avgMin: 14.4, overrideRate: 0.27, qaAgree: 0.88 },
    { r: "r-yuki", perDay: 44, avgMin: 9.9, overrideRate: 0.17, qaAgree: 0.94 },
  ] as const
).map((t) => ({ ...t, reviewer: REVIEWERS.find((x) => x.id === t.r)! }));

const COST: CostRow[] = (
  [
    { client: "halo", videos: 86, frames: 2510, tokens: 4.12e6, cost: 312.44, trend: [11, 9, 12, 10, 8, 7, 6.4] },
    { client: "cobalt", videos: 54, frames: 1602, tokens: 2.71e6, cost: 198.1, trend: [9, 9, 8, 8.5, 8, 7.5, 7.2] },
    { client: "meridian", videos: 41, frames: 1188, tokens: 1.94e6, cost: 141.77, trend: [7, 8, 7.5, 7, 6.8, 6.6, 6.5] },
    { client: "okta-v", videos: 33, frames: 902, tokens: 1.43e6, cost: 104.22, trend: [12, 11, 10, 9, 9, 8.4, 8.0] },
    { client: "northwind", videos: 22, frames: 668, tokens: 1.05e6, cost: 77.9, trend: [6, 7, 7, 8, 9, 9.5, 10] },
  ] as const
).map((c) => ({ ...c, trend: [...c.trend], clientObj: clientOf(c.client) }));

const JOBS: Job[] = (
  [
    { id: "job-9912", ref: "EGO-24820", stage: "frame_extract", status: "failed", attempts: 3, lastError: "ffmpeg: moov atom not found (truncated upload)", client: "cobalt", at: "08:41" },
    { id: "job-9908", ref: "EGO-24814", stage: "ai_grade", status: "failed", attempts: 2, lastError: "VLM timeout after 120s on frame 17", client: "halo", at: "08:12" },
    { id: "job-9901", ref: "EGO-24803", stage: "ai_grade", status: "dead", attempts: 5, lastError: "Rate limit exceeded — provider 429", client: "meridian", at: "07:55" },
    { id: "job-9897", ref: "EGO-24799", stage: "thumbnail", status: "running", attempts: 1, lastError: "", client: "meridian", at: "08:46" },
    { id: "job-9890", ref: "EGO-24788", stage: "ai_grade", status: "running", attempts: 1, lastError: "", client: "okta-v", at: "08:44" },
  ] as const
).map((j) => ({ ...j, clientObj: clientOf(j.client) }));

const SOURCES: Source[] = (
  [
    { id: "src-halo-shift", type: "s3", label: "Halo — daily shift uploads", uri: "s3://evas-videos/halo/shift/", cred: "halo-readonly", client: "halo", status: "syncing", autoSync: true, lastSync: 2, total: 412, done: 318, inReview: 24, ingested: 41, toGo: 29, failed: 0 },
    { id: "src-cobalt-lab", type: "s3", label: "Cobalt — embodied lab runs", uri: "s3://cobalt-embodied/sessions/2026/", cred: "cobalt-svc", client: "cobalt", status: "connected", autoSync: true, lastSync: 47, total: 286, done: 240, inReview: 18, ingested: 16, toGo: 9, failed: 3 },
    { id: "src-meridian-url", type: "url", label: "Meridian — partner manifest", uri: "https://cdn.meridianlabs.io/evas/manifest.json", cred: "meridian-token", client: "meridian", status: "connected", autoSync: false, lastSync: 1440, total: 142, done: 118, inReview: 11, ingested: 8, toGo: 5, failed: 0 },
    { id: "src-okta-drop", type: "s3", label: "Okta Vision — weekly drop", uri: "s3://okta-vision-evas/weekly/", cred: "okta-readonly", client: "okta-v", status: "error", autoSync: true, lastSync: 190, lastError: "AccessDenied: credential 'okta-readonly' lacks s3:ListBucket on okta-vision-evas", total: 73, done: 41, inReview: 9, ingested: 0, toGo: 23, failed: 0 },
    { id: "src-northwind", type: "s3", label: "Northwind — pilot batch", uri: "s3://northwind-ai/evas-pilot/", cred: "northwind-svc", client: "northwind", status: "disabled", autoSync: false, lastSync: 4320, total: 38, done: 22, inReview: 0, ingested: 0, toGo: 16, failed: 0 },
    { id: "src-cobalt-empty", type: "s3", label: "Cobalt — archive (new)", uri: "s3://cobalt-embodied/archive/", cred: "cobalt-svc", client: "cobalt", status: "connected", autoSync: false, lastSync: 12, total: 0, done: 0, inReview: 0, ingested: 0, toGo: 0, failed: 0 },
  ] as const
).map((s) => ({ ...s, clientObj: clientOf(s.client) }));

const CREDENTIALS = ["halo-readonly", "cobalt-svc", "meridian-token", "okta-readonly", "northwind-svc"];

const RUN_DEF = [
  { ref: "EGO-24820", client: "cobalt", model: "evas-vlm-3", prompt: "p-118", status: "running", done: 19, total: 28, scene: "lab", grade: null, flagged: 3, tokIn: 184000, tokOut: 22400, cost: 1.94, dur: null, started: 1 },
  { ref: "EGO-24788", client: "okta-v", model: "evas-vlm-3", prompt: "p-118", status: "running", done: 14, total: 22, scene: "desk", grade: null, flagged: 1, tokIn: 142000, tokOut: 16800, cost: 1.42, dur: null, started: 3 },
  { ref: "EGO-24799", client: "meridian", model: "evas-vlm-3", prompt: "p-118", status: "running", done: 22, total: 24, scene: "kitchen", grade: null, flagged: 2, tokIn: 156000, tokOut: 18900, cost: 1.61, dur: null, started: 4 },
  { ref: "EGO-24814", client: "halo", model: "evas-vlm-3", prompt: "p-118", status: "failed", done: 17, total: 30, scene: "street", grade: null, flagged: 4, tokIn: 121000, tokOut: 9200, cost: 1.18, dur: 72, started: 22, error: "VLM timeout after 120s on frame 17" },
  { ref: "EGO-24803", client: "meridian", model: "evas-vlm-3", prompt: "p-117", status: "failed", done: 0, total: 26, scene: "kitchen", grade: null, flagged: 0, tokIn: 0, tokOut: 0, cost: 0.0, dur: 4, started: 35, error: "Rate limit exceeded — provider 429 (5 retries)" },
  { ref: "EGO-24791", client: "halo", model: "evas-vlm-3", prompt: "p-118", status: "completed", done: 26, total: 26, scene: "market", grade: 7.5, flagged: 2, tokIn: 168000, tokOut: 20100, cost: 1.73, dur: 88, started: 51 },
  { ref: "EGO-24776", client: "meridian", model: "evas-vlm-3", prompt: "p-118", status: "completed", done: 20, total: 20, scene: "kitchen", grade: 8.0, flagged: 1, tokIn: 131000, tokOut: 15800, cost: 1.34, dur: 64, started: 67 },
  { ref: "EGO-24770", client: "okta-v", model: "evas-vlm-3", prompt: "p-118", status: "completed", done: 22, total: 22, scene: "desk", grade: 9.0, flagged: 0, tokIn: 139000, tokOut: 16400, cost: 1.41, dur: 70, started: 84 },
  { ref: "EGO-24762", client: "halo", model: "evas-vlm-2", prompt: "p-116", status: "completed", done: 28, total: 28, scene: "street", grade: 6.5, flagged: 5, tokIn: 201000, tokOut: 24200, cost: 2.38, dur: 119, started: 102 },
  { ref: "EGO-24744", client: "northwind", model: "evas-vlm-3", prompt: "p-118", status: "completed", done: 30, total: 30, scene: "garage", grade: 7.0, flagged: 3, tokIn: 188000, tokOut: 22600, cost: 1.93, dur: 96, started: 131 },
  { ref: "EGO-24731", client: "meridian", model: "evas-vlm-3", prompt: "p-117", status: "completed", done: 24, total: 24, scene: "lab", grade: 7.5, flagged: 2, tokIn: 151000, tokOut: 18100, cost: 1.55, dur: 78, started: 156 },
  { ref: "EGO-24722", client: "cobalt", model: "evas-vlm-3", prompt: "p-118", status: "completed", done: 18, total: 18, scene: "lab", grade: 8.5, flagged: 0, tokIn: 118000, tokOut: 14200, cost: 1.21, dur: 58, started: 178 },
] as const;

const AI_RUNS: AiRun[] = RUN_DEF.map((r, i) => ({
  id: "run-" + (8840 - i),
  ...r,
  error: "error" in r ? (r as { error: string }).error : undefined,
  clientObj: clientOf(r.client),
  sceneLabel: SCENES.find((s) => s.id === r.scene)!.label,
  tokens: r.tokIn + r.tokOut,
}));

const AI_QUEUED = 7;

const AI_STATS: AiStats = {
  byModel: [
    { key: "evas-vlm-3", videosHr: 4.2, costVideo: 1.58, avgConf: 0.88, flaggedRate: 0.094, errRate: 0.041, spark: { videosHr: [3.6, 3.8, 4.0, 3.9, 4.1, 4.3, 4.2], costVideo: [1.9, 1.8, 1.74, 1.68, 1.62, 1.6, 1.58], conf: [0.84, 0.85, 0.86, 0.87, 0.87, 0.88, 0.88], flagged: [0.11, 0.105, 0.1, 0.098, 0.096, 0.095, 0.094], err: [0.06, 0.055, 0.05, 0.048, 0.044, 0.042, 0.041] } },
    { key: "evas-vlm-2", videosHr: 3.1, costVideo: 2.34, avgConf: 0.81, flaggedRate: 0.151, errRate: 0.082, spark: { videosHr: [3.0, 3.0, 3.1, 3.05, 3.1, 3.1, 3.1], costVideo: [2.4, 2.38, 2.36, 2.35, 2.34, 2.34, 2.34], conf: [0.8, 0.8, 0.81, 0.81, 0.81, 0.81, 0.81], flagged: [0.16, 0.158, 0.155, 0.153, 0.152, 0.151, 0.151], err: [0.09, 0.088, 0.085, 0.084, 0.083, 0.082, 0.082] } },
  ],
  byPrompt: [
    { key: "p-118", videosHr: 4.4, costVideo: 1.52, avgConf: 0.89, flaggedRate: 0.088, errRate: 0.038, spark: { videosHr: [4.0, 4.1, 4.2, 4.3, 4.3, 4.4, 4.4], costVideo: [1.62, 1.58, 1.56, 1.54, 1.53, 1.52, 1.52], conf: [0.86, 0.87, 0.88, 0.88, 0.89, 0.89, 0.89], flagged: [0.1, 0.097, 0.094, 0.091, 0.09, 0.089, 0.088], err: [0.05, 0.046, 0.043, 0.041, 0.039, 0.038, 0.038] } },
    { key: "p-117", videosHr: 3.9, costVideo: 1.71, avgConf: 0.85, flaggedRate: 0.118, errRate: 0.061, spark: { videosHr: [3.7, 3.8, 3.8, 3.9, 3.9, 3.9, 3.9], costVideo: [1.8, 1.77, 1.75, 1.73, 1.72, 1.71, 1.71], conf: [0.83, 0.84, 0.84, 0.85, 0.85, 0.85, 0.85], flagged: [0.13, 0.127, 0.124, 0.121, 0.12, 0.119, 0.118], err: [0.08, 0.075, 0.07, 0.066, 0.063, 0.062, 0.061] } },
    { key: "p-116", videosHr: 3.4, costVideo: 2.12, avgConf: 0.82, flaggedRate: 0.142, errRate: 0.079, spark: { videosHr: [3.3, 3.3, 3.4, 3.4, 3.4, 3.4, 3.4], costVideo: [2.2, 2.18, 2.16, 2.14, 2.13, 2.12, 2.12], conf: [0.81, 0.81, 0.82, 0.82, 0.82, 0.82, 0.82], flagged: [0.15, 0.148, 0.146, 0.144, 0.143, 0.142, 0.142], err: [0.09, 0.087, 0.084, 0.082, 0.08, 0.079, 0.079] } },
  ],
};

function getRun(id: string): AiRunDetail {
  const r = AI_RUNS.find((x) => x.id === id) ?? AI_RUNS[0];
  SEED = 200 + parseInt(r.ref.slice(-3), 10);
  const flaggedIdx: number[] = [];
  for (let i = 0; i < r.flagged; i++) flaggedIdx.push(Math.floor((i + 1) * (r.total / (r.flagged + 1))));
  const allFrames = buildFrames(r.scene, r.total, flaggedIdx);
  const doneFrames = allFrames.slice(0, r.done);
  return { ...r, frames: doneFrames, allCount: r.total };
}

const PORTAL_VIDEOS: PortalVideo[] = [
  { ref: "EGO-24799", uploaded: "Jun 6, 2026", status: "reviewed", grade: 8.5, scene: "kitchen" },
  { ref: "EGO-24776", uploaded: "Jun 6, 2026", status: "reviewed", grade: 8.0, scene: "kitchen" },
  { ref: "EGO-24791", uploaded: "Jun 5, 2026", status: "in_review", grade: null, scene: "market" },
  { ref: "EGO-24770", uploaded: "Jun 5, 2026", status: "reviewed", grade: 9.0, scene: "desk" },
  { ref: "EGO-24762", uploaded: "Jun 4, 2026", status: "reviewed", grade: 6.5, scene: "street" },
  { ref: "EGO-24744", uploaded: "Jun 4, 2026", status: "processing", grade: null, scene: "garage" },
  { ref: "EGO-24731", uploaded: "Jun 3, 2026", status: "reviewed", grade: 7.5, scene: "lab" },
];

export const D = {
  CLIENTS,
  REVIEWERS,
  CURRENT,
  CHECKLIST,
  SCENES,
  QUEUE,
  getReview,
  PIPELINE,
  DISCREPANCY,
  THROUGHPUT,
  COST,
  JOBS,
  PORTAL_VIDEOS,
  SOURCES,
  CREDENTIALS,
  AI_RUNS,
  AI_QUEUED,
  AI_STATS,
  getRun,
  clientOf,
  tc,
};

export function sceneOf(id: string): Scene {
  return SCENES.find((s) => s.id === id) ?? SCENES[0];
}
