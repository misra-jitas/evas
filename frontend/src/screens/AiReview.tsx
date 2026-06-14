// AI Review (admin) — agent observability: pulse band, aggregate strip, runs
// log, run drill-down. Runs list + Re-run hit the live API (GET /ai/runs,
// POST /ai/runs/{id}/rerun); the sparkline aggregate strip and drill-down keep
// the prototype's rich mock visuals (the live /ai/stats has no spark series).
import { useEffect, useState } from "react";
import { api, type ChecklistConfig, useLive } from "../api";
import {
  Btn,
  ClientChip,
  ConfBar,
  CostLine,
  EmptyInline,
  FrameThumb,
  Grade,
  Ico,
  Legend,
  Row,
  Segment,
  Select,
  Spark,
  StatusBadge,
  Tag,
} from "../components";
import { sceneOf } from "../data";
import type { AiRun, AiRunDetail, AiStatGroup, AiStats, TFn } from "../types";

export function AIReviewScreen({
  t,
  sub,
  runId,
  onOpen,
  onOpenDiscrepancy,
}: {
  t: TFn;
  sub: "list" | "run";
  runId?: string;
  onOpen: (screen: "aireview" | "run", id?: string) => void;
  onOpenDiscrepancy: () => void;
}) {
  const live = useLive<AiRun[]>(() => api.listRuns(), []);
  const statsLive = useLive<AiStats>(() => api.runStats(), { byModel: [], byPrompt: [] });
  const metricsLive = useLive<{ queue_depth: number } | null>(() => api.adminMetrics(), null);
  const [runs, setRuns] = useState<AiRun[]>(live.data);
  const [groupBy, setGroupBy] = useState("model");
  const [fStatus, setFStatus] = useState("all");
  const [fClient, setFClient] = useState("all");
  const [hasIssues, setHasIssues] = useState(false);

  useEffect(() => setRuns(live.data), [live.data]);

  useEffect(() => {
    const iv = setInterval(() => {
      setRuns((prev) =>
        prev.map((r) => {
          if (r.status !== "running") return r;
          const done = Math.min(r.total, r.done + 1);
          return { ...r, done, status: done >= r.total ? "completed" : "running", grade: done >= r.total ? Math.round((6 + Math.random() * 3) * 2) / 2 : null };
        }),
      );
    }, 2200);
    return () => clearInterval(iv);
  }, []);

  if (sub === "run" && runId) {
    return <RunDetail t={t} runId={runId} onBack={() => onOpen("aireview")} onOpenDiscrepancy={onOpenDiscrepancy} />;
  }

  const running = runs.filter((r) => r.status === "running");
  const runningFrames = running.reduce((s, r) => s + r.total, 0);
  const doneToday = runs.filter((r) => r.status === "completed").length;
  const issues = runs.filter((r) => r.status === "failed").length;

  const rows = runs.filter(
    (r) => (fStatus === "all" || r.status === fStatus) && (fClient === "all" || r.client === fClient) && (!hasIssues || r.status === "failed" || r.flagged >= 4),
  );

  const stats = groupBy === "model" ? statsLive.data.byModel : statsLive.data.byPrompt;

  function rerun(r: AiRun) {
    api.rerun(r.id).catch(() => {});
    setRuns((prev) => [{ ...r, id: "run-" + Date.now(), status: "running", done: 0, grade: null, error: undefined, started: 0 }, ...prev]);
  }

  return (
    <div style={{ height: "100%", overflow: "auto", background: "var(--bg)" }}>
      <div style={{ maxWidth: 1280, margin: "0 auto", padding: "24px 28px 60px" }}>
        <div style={{ marginBottom: 18 }}>
          <div className="label" style={{ marginBottom: 6 }}>{t("role.admin")}</div>
          <h1 style={{ fontSize: 26, letterSpacing: "-0.02em" }}>{t("ai.title")}</h1>
          <p style={{ color: "var(--ink-3)", fontSize: 13, marginTop: 4 }}>{t("ai.sub")}</p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 16 }}>
          <PulseCard label={t("ai.inprogress")} icon="pulse" tone="var(--accent)" live value={running.length} unit={t("ai.running")} sub={`${runningFrames.toLocaleString()} ${t("ai.frames")}`} />
          <PulseCard label={t("ai.queued")} icon="clock" tone="var(--ink-2)" value={metricsLive.data?.queue_depth ?? 0} unit="jobs queued" sub="waiting to start" />
          <PulseCard label={t("ai.donetoday")} icon="check" tone="var(--green)" value={doneToday} unit="runs" sub={`${doneToday} videos graded`} />
          <PulseCard label={t("ai.issues")} icon="alert" tone={issues > 0 ? "var(--red)" : "var(--ink-3)"} value={issues} unit="failed" sub={issues > 0 ? "click to filter" : "all healthy"} alarm={issues > 0} onClick={issues > 0 ? () => { setFStatus("failed"); setHasIssues(false); } : undefined} />
        </div>

        <div className="panel" style={{ padding: 16, marginBottom: 22 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
            <h2 style={{ fontSize: 13.5, display: "flex", alignItems: "center", gap: 8, fontWeight: 600 }}>
              <Ico name="activity" size={15} stroke="var(--ink-3)" /> Aggregate · last 7 days
            </h2>
            <Segment value={groupBy} onChange={setGroupBy} options={[{ value: "model", label: t("ai.bymodel") }, { value: "prompt", label: t("ai.byprompt") }]} />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "minmax(110px, 0.8fr) repeat(5, 1fr)", gap: 1, background: "var(--line)", border: "1px solid var(--line)", borderRadius: 6, overflow: "hidden" }}>
            <div style={{ background: "var(--panel-2)", padding: "9px 12px" }} className="label">{groupBy === "model" ? t("ai.model") : t("ai.byprompt")}</div>
            {[t("ai.videoshr"), t("ai.costvideo"), t("ai.avgconf"), t("ai.flaggedrate"), t("ai.errrate")].map((h) => (
              <div key={h} style={{ background: "var(--panel-2)", padding: "9px 12px" }} className="label">{h}</div>
            ))}
            {stats.map((g: AiStatGroup) => (
              <FragmentRow key={g.key} g={g} />
            ))}
          </div>
          <p style={{ fontSize: 11.5, color: "var(--ink-4)", marginTop: 10, display: "flex", alignItems: "center", gap: 6 }}>
            <Ico name="bolt" size={12} /> Promote the prompt that flags less at higher confidence for the same cost — this strip is the A/B feed.
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10, flexWrap: "wrap", gap: 10 }}>
          <h2 style={{ fontSize: 13.5, display: "flex", alignItems: "center", gap: 8, fontWeight: 600 }}>
            <Ico name="cpu" size={15} stroke="var(--ink-3)" /> {t("ai.runs")} <span className="mono tnum" style={{ color: "var(--ink-3)", fontWeight: 400 }}>{rows.length}</span>
          </h2>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <Select value={fStatus} onChange={setFStatus} icon="filter" options={[{ v: "all", l: "All status" }, { v: "running", l: "Running" }, { v: "completed", l: "Completed" }, { v: "failed", l: "Failed" }]} />
            <Select value={fClient} onChange={setFClient} options={[{ v: "all", l: t("common.all") }, ...Array.from(new Map(runs.map((r) => [r.client, r.clientObj.name])).entries()).map(([id, name]) => ({ v: id, l: name }))]} />
            <button onClick={() => setHasIssues((v) => !v)} style={{ display: "flex", alignItems: "center", gap: 7, padding: "7px 11px", borderRadius: 4, fontSize: 12.5, fontWeight: 550, border: `1px solid ${hasIssues ? "var(--red)" : "var(--line-strong)"}`, background: hasIssues ? "var(--red-bg)" : "var(--panel)", color: hasIssues ? "var(--red)" : "var(--ink-2)" }}>
              <Ico name="alert" size={14} /> {t("ai.hasissues")}
            </button>
          </div>
        </div>
        <div className="panel" style={{ overflow: "hidden" }}>
          <Row head cols="52px 1.05fr 1fr 132px 64px 70px 120px 78px 78px">
            {["", t("queue.ref"), `${t("ai.model")} · prompt`, t("ai.status"), t("ai.grade"), t("queue.flagged"), t("ai.tokens") + " · " + t("ai.cost"), t("ai.duration"), t("ai.started")].map((h, i) => (
              <span key={i} className="label" style={{ textAlign: i === 4 || i === 5 ? "right" : "left" }}>{h}</span>
            ))}
          </Row>
          {rows.length === 0 ? (
            <EmptyInline icon="cpu" msg={runs.length === 0 ? "No AI runs yet — they appear as videos are reviewed." : "No runs match these filters"} />
          ) : (
            rows.map((r, i) => <RunRow key={r.id} r={r} t={t} last={i === rows.length - 1} onClick={() => onOpen("run", r.id)} onRerun={() => rerun(r)} />)
          )}
        </div>
      </div>
    </div>
  );
}

function FragmentRow({ g }: { g: AiStatGroup }) {
  return (
    <>
      <div style={{ background: "var(--panel)", padding: "11px 12px", display: "flex", alignItems: "center" }}>
        <span className="mono" style={{ fontSize: 12, fontWeight: 600, padding: "2px 7px", borderRadius: 3, background: "var(--panel-3)" }}>{g.key}</span>
      </div>
      <MetricCell value={g.videosHr.toFixed(1)} spark={g.spark.videosHr} up />
      <MetricCell value={`$${g.costVideo.toFixed(2)}`} spark={g.spark.costVideo} />
      <MetricCell value={`${Math.round(g.avgConf * 100)}%`} spark={g.spark.conf} up />
      <MetricCell value={`${(g.flaggedRate * 100).toFixed(1)}%`} spark={g.spark.flagged} tone="var(--amber)" />
      <MetricCell value={`${(g.errRate * 100).toFixed(1)}%`} spark={g.spark.err} tone="var(--red)" />
    </>
  );
}

function PulseCard({ label, icon, tone, value, unit, sub, live, alarm, onClick }: { label: string; icon: string; tone: string; value: number; unit: string; sub: string; live?: boolean; alarm?: boolean; onClick?: () => void }) {
  return (
    <button onClick={onClick} disabled={!onClick} style={{ textAlign: "left", border: "1px solid var(--line)", background: "var(--panel)", borderRadius: 6, padding: "14px 15px", cursor: onClick ? "pointer" : "default", boxShadow: "var(--shadow-1)", position: "relative", overflow: "hidden", borderColor: alarm ? "var(--red)" : "var(--line)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 10 }}>
        <Ico name={icon} size={14} stroke={tone} style={live && value > 0 ? { animation: "evas-blink 1.4s steps(1) infinite" } : undefined} />
        <span className="label" style={{ color: "var(--ink-2)" }}>{label}</span>
        {live && value > 0 && <span className="rec-dot" style={{ width: 6, height: 6, borderRadius: 99, background: tone, marginLeft: "auto" }} />}
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}>
        <span className="mono tnum" style={{ fontSize: 30, fontWeight: 600, color: tone, lineHeight: 1 }}>{value}</span>
        <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{unit}</span>
      </div>
      <div style={{ fontSize: 11.5, color: "var(--ink-4)", marginTop: 6 }}>{sub}</div>
    </button>
  );
}

function MetricCell({ value, spark, up, tone }: { value: string; spark: number[]; up?: boolean; tone?: string }) {
  const rising = spark[spark.length - 1] >= spark[0];
  const good = up ? rising : !rising;
  const sparkTone = tone || (good ? "var(--green)" : "var(--amber)");
  return (
    <div style={{ background: "var(--panel)", padding: "10px 12px" }}>
      <div className="mono tnum" style={{ fontSize: 15, fontWeight: 600, color: tone || "var(--ink)" }}>{value}</div>
      <div style={{ marginTop: 5 }}><Spark data={spark} w={68} h={18} tone={sparkTone} /></div>
    </div>
  );
}

function RunRow({ r, t, last, onClick, onRerun }: { r: AiRun; t: TFn; last: boolean; onClick: () => void; onRerun: () => void }) {
  const running = r.status === "running";
  const failed = r.status === "failed";
  return (
    <div onClick={onClick} style={{ borderBottom: last ? "none" : "1px solid var(--line-2)", cursor: "pointer" }} onMouseEnter={(e) => (e.currentTarget.style.background = "var(--panel-2)")} onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
      <div style={{ display: "grid", gridTemplateColumns: "52px 1.05fr 1fr 132px 64px 70px 120px 78px 78px", gap: 12, alignItems: "center", padding: "10px 14px" }}>
        <FrameThumb frame={{ hue: sceneOf(r.scene).hue }} style={{ width: 44, height: 26 }} showHud={false} />
        <div style={{ minWidth: 0 }}>
          <div className="mono" style={{ fontSize: 12.5, fontWeight: 600 }}>{r.ref}</div>
          <div style={{ marginTop: 2 }}><ClientChip client={r.clientObj} mono /></div>
        </div>
        <span style={{ minWidth: 0 }}>
          <span className="mono" style={{ display: "block", fontSize: 11.5, color: "var(--ink-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.model} · {r.prompt}</span>
          <span className="mono" style={{ display: "block", fontSize: 10.5, color: "var(--ink-3)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {r.checklistName} v{r.checklistVersion}{r.promptCustom ? " · custom" : ""}
          </span>
        </span>
        <div>
          <StatusBadge status={r.status} size="sm" />
          {running && (
            <div style={{ marginTop: 5, display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ flex: 1, height: 4, borderRadius: 99, background: "var(--line)", overflow: "hidden", maxWidth: 70 }}>
                <span style={{ display: "block", width: `${(r.done / r.total) * 100}%`, height: "100%", background: "var(--accent)", transition: "width .4s" }} />
              </span>
              <span className="mono tnum" style={{ fontSize: 10, color: "var(--ink-3)" }}>{r.done}/{r.total}</span>
            </div>
          )}
        </div>
        <span style={{ textAlign: "right" }}><Grade value={r.grade} size={12.5} /></span>
        <span style={{ textAlign: "right" }}>
          {r.flagged > 0 ? (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 3, color: r.flagged >= 4 ? "var(--amber)" : "var(--ink-2)" }}>
              <Ico name="flag" size={11} fill={r.flagged >= 4 ? "var(--amber)" : "none"} stroke={r.flagged >= 4 ? "none" : "var(--ink-3)"} />
              <span className="mono tnum" style={{ fontSize: 12, fontWeight: 600 }}>{r.flagged}</span>
            </span>
          ) : (
            <span className="mono" style={{ color: "var(--ink-4)" }}>0</span>
          )}
        </span>
        <span className="mono tnum" style={{ fontSize: 11, color: "var(--ink-2)" }}>{(r.tokens / 1000).toFixed(0)}k · ${r.cost.toFixed(2)}</span>
        <span className="mono tnum" style={{ fontSize: 11.5, color: "var(--ink-2)" }}>{r.dur == null ? "—" : r.dur + "s"}</span>
        <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>{r.started === 0 ? "now" : r.started + "m"}</span>
      </div>
      {failed && r.error && (
        <div onClick={(e) => e.stopPropagation()} style={{ display: "flex", alignItems: "center", gap: 10, padding: "0 14px 11px 66px" }}>
          <span style={{ flex: 1, display: "flex", alignItems: "center", gap: 8, padding: "7px 11px", borderRadius: 5, background: "var(--red-bg)", minWidth: 0 }}>
            <Ico name="alert" size={13} stroke="var(--red)" style={{ flexShrink: 0 }} />
            <span className="mono" style={{ fontSize: 11, color: "var(--red)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.error}</span>
          </span>
          <Btn kind="default" size="sm" icon="refresh" onClick={onRerun}>{t("ai.rerun")}</Btn>
        </div>
      )}
    </div>
  );
}

function RunDetail({ t, runId, onBack, onOpenDiscrepancy }: { t: TFn; runId: string; onBack: () => void; onOpenDiscrepancy: () => void }) {
  const detail = useLive<AiRunDetail | null>(() => api.runDetail(runId), null, [runId]);
  const run = detail.data;
  const [selFrame, setSelFrame] = useState<string | null>(null);
  // Re-run controls: optionally against a different checklist version of this client.
  const clId = run?.client || "";
  const checklists = useLive<ChecklistConfig[]>(
    () => (clId ? api.listChecklists(clId) : Promise.resolve([])),
    [],
    [clId],
  );
  const [rerunChecklist, setRerunChecklist] = useState<string>("");
  const [rerunBusy, setRerunBusy] = useState(false);
  // Send-to-human controls.
  const reviewers = useLive<{ id: string; name: string; role: string }[]>(() => api.listReviewers(), [], []);
  const [reviewerId, setReviewerId] = useState("");
  const [sendBusy, setSendBusy] = useState(false);
  const [sent, setSent] = useState(false);
  useEffect(() => {
    if (run && run.frames[0]) setSelFrame((cur) => cur ?? run.frames[0].id);
  }, [run]);

  function sendToHuman() {
    if (!run || !reviewerId) return;
    setSendBusy(true);
    api
      .sendToHuman(run.id, reviewerId)
      .then(() => setSent(true))
      .catch(() => {})
      .finally(() => setSendBusy(false));
  }

  function doRerun() {
    if (!run) return;
    setRerunBusy(true);
    const body = rerunChecklist ? { checklist_id: rerunChecklist } : undefined;
    api
      .rerun(run.id, body)
      .then(() => onBack())
      .catch(() => {})
      .finally(() => setRerunBusy(false));
  }

  if (!run) {
    return (
      <div style={{ height: "100%", overflow: "auto", background: "var(--bg)" }}>
        <div style={{ maxWidth: 1180, margin: "0 auto", padding: "24px 28px" }}>
          <Btn kind="ghost" size="sm" icon="arrowL" onClick={onBack} style={{ marginBottom: 14, marginLeft: -6 }}>{t("ai.title")}</Btn>
          <div className="panel" style={{ padding: 40, textAlign: "center", color: "var(--ink-4)" }}>
            {detail.loading ? t("common.loading") + "…" : "Run not found."}
          </div>
        </div>
      </div>
    );
  }

  const scene = sceneOf(run.scene);
  const selected = run.frames.find((f) => f.id === selFrame) || run.frames[0];

  // Real human grade + gap from the API (null until a human has reviewed).
  const humanGrade = run.humanGrade;
  const gap = run.gradeGap;
  const lowConf = run.frames.filter((f) => f.items.some((i) => i.conf < 0.6));
  const tokPerFrame = run.frames.length ? run.cost / run.frames.length : 0;

  return (
    <div style={{ height: "100%", overflow: "auto", background: "var(--bg)" }}>
      <div style={{ maxWidth: 1180, margin: "0 auto", padding: "24px 28px 60px" }}>
        <Btn kind="ghost" size="sm" icon="arrowL" onClick={onBack} style={{ marginBottom: 14, marginLeft: -6 }}>{t("ai.title")}</Btn>

        <div className="panel" style={{ padding: 18, marginBottom: 18 }}>
          <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
            <FrameThumb frame={selected || { hue: scene.hue, timecode: "00:00:00", flagged: false }} large style={{ width: 220, aspectRatio: "16/10", flexShrink: 0 }} />
            <div style={{ flex: 1, minWidth: 240 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <h1 className="mono" style={{ fontSize: 20, whiteSpace: "nowrap" }}>{run.ref}</h1>
                <ClientChip client={run.clientObj} />
                <StatusBadge status={run.status} label={t("ai." + run.status)} />
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                <Tag label={t("ai.model")} value={run.model} />
                <Tag label="prompt" value={run.prompt + (run.promptCustom ? " · custom" : "")} />
                <Tag label="checklist" value={`${run.checklistName} v${run.checklistVersion}`} />
                <Tag label={t("ai.tokens")} value={(run.tokens / 1000).toFixed(0) + "k"} />
                <Tag label={t("ai.cost")} value={"$" + run.cost.toFixed(2)} />
                <Tag label={t("ai.duration")} value={run.dur == null ? "running" : run.dur + "s"} />
              </div>
              {run.grade != null && (
                <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 14 }}>
                  <div>
                    <div className="label" style={{ marginBottom: 3 }}>AI {t("ai.grade")}</div>
                    <Grade value={run.grade} size={30} />
                  </div>
                  {gap != null && (
                    <button onClick={onOpenDiscrepancy} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 13px", borderRadius: 6, border: "1px solid var(--line-strong)", background: "var(--panel-2)", cursor: "pointer" }}>
                      <div style={{ textAlign: "left" }}>
                        <div className="label" style={{ marginBottom: 3 }}>{t("ai.vshuman")}</div>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <Grade value={run.grade} size={13} muted /><span style={{ color: "var(--ink-4)" }}>→</span>
                          <Grade value={humanGrade} size={13} muted />
                          <span className="mono tnum" style={{ fontSize: 12, fontWeight: 700, color: gap >= 3 ? "var(--red)" : "var(--amber)" }}>Δ{gap.toFixed(1)}</span>
                        </div>
                      </div>
                      <Ico name="arrowR" size={15} stroke="var(--accent)" />
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
          {run.error && (
            <div style={{ marginTop: 14, padding: "10px 13px", borderRadius: 6, background: "var(--red-bg)", display: "flex", gap: 9, alignItems: "center" }}>
              <Ico name="alert" size={15} stroke="var(--red)" style={{ flexShrink: 0 }} />
              <span className="mono" style={{ fontSize: 12, color: "var(--red)" }}>{run.error}</span>
            </div>
          )}
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--line-2)", flexWrap: "wrap" }}>
            <span className="label">Re-run review</span>
            <Select
              value={rerunChecklist}
              onChange={setRerunChecklist}
              options={[
                { v: "", l: "Same checklist (re-review)" },
                ...checklists.data.map((c) => ({ v: c.id, l: `${c.name} v${c.version}${c.is_active ? " · active" : ""}` })),
              ]}
            />
            <Btn kind="default" size="sm" icon="refresh" disabled={rerunBusy} onClick={doRerun}>
              {rerunBusy ? "Queuing…" : "Re-run"}
            </Btn>
            <span style={{ fontSize: 11, color: "var(--ink-4)" }}>Creates a new run; history is preserved.</span>
          </div>
        </div>

        <div className="label" style={{ marginBottom: 9 }}>{t("ai.timeline")} · <span style={{ color: "var(--ink-2)" }}>{run.frames.length}/{run.allCount} {t("ai.frames")}</span></div>
        <div className="panel" style={{ padding: 14, marginBottom: 8 }}>
          <div style={{ display: "flex", gap: 3, alignItems: "flex-end", overflowX: "auto", paddingBottom: 4 }}>
            {run.frames.map((f) => {
              const mc = Math.min(...f.items.map((i) => i.conf));
              const tone = mc >= 0.75 ? "var(--green)" : mc >= 0.6 ? "var(--amber)" : "var(--red)";
              const h = 18 + mc * 38;
              const sel = f.id === selFrame;
              return (
                <button key={f.id} onClick={() => setSelFrame(f.id)} title={`${f.timecode} · conf ${Math.round(mc * 100)}%`} style={{ flexShrink: 0, width: 13, padding: 0, border: "none", background: "transparent", cursor: "pointer", display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
                  {f.flagged && <Ico name="flag" size={9} fill="var(--amber)" stroke="none" />}
                  <span style={{ width: sel ? 11 : 9, height: h, borderRadius: 2, background: tone, outline: sel ? "2px solid var(--ink)" : "none", outlineOffset: 1, transition: "all .1s", opacity: sel ? 1 : 0.82 }} />
                </button>
              );
            })}
            {Array.from({ length: run.allCount - run.frames.length }).map((_, i) => (
              <span key={"r" + i} style={{ flexShrink: 0, width: 9, height: 18, borderRadius: 2, border: "1px dashed var(--line-strong)", marginBottom: 12 }} />
            ))}
          </div>
          <div style={{ display: "flex", gap: 16, marginTop: 12, fontSize: 11, color: "var(--ink-3)" }}>
            <Legend c="var(--green)" l="high conf ≥75%" />
            <Legend c="var(--amber)" l="med 60–75%" />
            <Legend c="var(--red)" l="low <60%" />
            <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><Ico name="flag" size={11} fill="var(--amber)" stroke="none" /> flagged</span>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 18, alignItems: "start", marginTop: 18 }}>
          <div>
            <div className="label" style={{ marginBottom: 9 }}>What the agent said · frame {selected ? selected.idx + 1 : "—"}</div>
            {selected && (
              <div className="panel" style={{ overflow: "hidden" }}>
                <div style={{ display: "flex", gap: 13, padding: 13, borderBottom: "1px solid var(--line-2)" }}>
                  <FrameThumb frame={selected} style={{ width: 120, aspectRatio: "16/10", flexShrink: 0 }} large={false} />
                  <div style={{ minWidth: 0 }}>
                    <span className="mono" style={{ fontSize: 11, color: "var(--accent)", fontWeight: 600 }}>{selected.timecode}</span>
                    <p style={{ margin: "5px 0 0", fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.5 }}>{selected.desc}</p>
                  </div>
                </div>
                {selected.items.map((it, i) => {
                  // Color by AI compliance: false → red, true → neutral, null (text/no target) → muted.
                  const bad = it.compliant === false;
                  return (
                    <div key={it.key} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 13px", borderBottom: i < selected.items.length - 1 ? "1px solid var(--line-2)" : "none" }}>
                      <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.label}</span>
                        <span className="label" style={{ fontSize: 9, flexShrink: 0 }}>{it.itemType && it.itemType !== "boolean" ? it.itemType : ""}</span>
                      </span>
                      <span className="mono" title={it.display} style={{ maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 11, fontWeight: 600, padding: "1px 6px", borderRadius: 3, background: bad ? "var(--red-bg)" : "var(--panel-3)", color: bad ? "var(--red)" : "var(--ink-2)" }}>{it.display ?? it.aiValue}</span>
                      <ConfBar v={it.conf} />
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <div>
              <div className="label" style={{ marginBottom: 9 }}>Send to human review</div>
              <div className="panel" style={{ padding: 14 }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                  <span className="mono tnum" style={{ fontSize: 22, fontWeight: 700, color: run.triage.count ? "var(--amber)" : "var(--green)" }}>{run.triage.count}</span>
                  <span style={{ fontSize: 12.5, color: "var(--ink-2)" }}>frames to verify</span>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px", marginTop: 8, fontSize: 11.5, color: "var(--ink-3)" }}>
                  <span><b style={{ color: "var(--ink-2)" }}>{run.triage.lowConfidence}</b> low-confidence</span>
                  <span><b style={{ color: "var(--ink-2)" }}>{run.triage.nonCompliant}</b> AI-failed</span>
                  <span><b style={{ color: "var(--ink-2)" }}>{run.triage.sample}</b> sampled</span>
                </div>
                {sent ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12, color: "var(--green)", fontSize: 12.5 }}>
                    <Ico name="check" size={15} /> Assigned to a reviewer.
                  </div>
                ) : (
                  <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                    <Select
                      value={reviewerId}
                      onChange={setReviewerId}
                      options={[{ v: "", l: "Pick reviewer…" }, ...reviewers.data.map((u) => ({ v: u.id, l: `${u.name} (${u.role})` }))]}
                    />
                    <Btn kind="primary" size="sm" icon="user" disabled={!reviewerId || sendBusy} onClick={sendToHuman}>
                      {sendBusy ? "Assigning…" : "Send"}
                    </Btn>
                  </div>
                )}
              </div>
            </div>
            <div>
              <div className="label" style={{ marginBottom: 9 }}>{t("ai.issuespanel")}</div>
              <div className="panel" style={{ padding: 14 }}>
                {lowConf.length === 0 ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--green)", fontSize: 12.5 }}>
                    <Ico name="check" size={15} /> No low-confidence frames or parse errors.
                  </div>
                ) : (
                  <>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--amber)", fontSize: 12.5, marginBottom: 10 }}>
                      <Ico name="alert" size={15} /> {lowConf.length} frames below 60% confidence
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {lowConf.map((f) => (
                        <button key={f.id} onClick={() => setSelFrame(f.id)} className="mono" style={{ fontSize: 10.5, padding: "3px 7px", borderRadius: 3, border: "1px solid var(--amber)", background: "var(--amber-bg)", color: "var(--amber)", cursor: "pointer" }}>{f.timecode}</button>
                      ))}
                    </div>
                  </>
                )}
                {run.error && (
                  <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--line-2)", display: "flex", alignItems: "center", gap: 8, color: "var(--red)", fontSize: 12 }}>
                    <Ico name="x" size={14} /> 1 run-level error · {run.status === "failed" ? "no retries left" : "retried"}
                  </div>
                )}
              </div>
            </div>
            <div>
              <div className="label" style={{ marginBottom: 9 }}>{t("ai.costbreak")}</div>
              <div className="panel" style={{ padding: 14, display: "flex", flexDirection: "column", gap: 10 }}>
                <CostLine label={t("ai.tokin")} value={run.tokIn.toLocaleString()} />
                <CostLine label={t("ai.tokout")} value={run.tokOut.toLocaleString()} />
                <CostLine label={t("ai.perframe")} value={"$" + tokPerFrame.toFixed(3)} />
                <div style={{ display: "flex", justifyContent: "space-between", paddingTop: 10, borderTop: "1px solid var(--line-2)" }}>
                  <span className="label" style={{ alignSelf: "center" }}>{t("ai.cost")}</span>
                  <span className="mono tnum" style={{ fontSize: 16, fontWeight: 700 }}>${run.cost.toFixed(2)}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
