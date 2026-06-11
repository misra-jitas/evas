// Ops Dashboard (admin): pipeline + discrepancy from the live video board
// (GET /videos), Jobs from GET /admin/metrics, plus /videos sub-view. Cost and
// reviewer-throughput have no API endpoint yet and show honest empty states.
import { useState } from "react";
import { api, useLive } from "../api";
import { ClientChip, EmptyInline, FrameThumb, Grade, Ico, Row, SearchBox, Select } from "../components";
import { sceneOf } from "../data";
import type { BoardVideo, TFn } from "../types";

interface Metrics {
  dead_jobs: number;
  queue_depth: number;
  running_jobs: number;
  webhook_failures: number;
}

const STAGES: { key: string; label: string; tone: string }[] = [
  { key: "ingested", label: "Ingested", tone: "ink" },
  { key: "frames_extracted", label: "Frames out", tone: "ink" },
  { key: "ai_reviewed", label: "AI reviewed", tone: "accent" },
  { key: "human_reviewed", label: "Human reviewed", tone: "amber" },
  { key: "done", label: "Done", tone: "green" },
  { key: "failed", label: "Failed", tone: "red" },
];

export function DashboardScreen({ t, sub, onOpenReview }: { t: TFn; sub: string | null; onOpenReview: (id: string) => void }) {
  const [threshold, setThreshold] = useState(2);
  const [client, setClient] = useState("all");
  const board = useLive<BoardVideo[]>(() => api.boardVideos(), []);

  if (sub === "videos") return <VideosView t={t} onOpenReview={onOpenReview} />;
  if (sub === "jobs") return <JobsView t={t} />;

  const videos = board.data;
  const pipeline = STAGES.map((s) => ({ ...s, count: videos.filter((v) => v.status === s.key).length }));
  const clientOpts = [
    { v: "all", l: t("common.all") },
    ...Array.from(new Map(videos.map((v) => [v.clientId, v.clientObj.name])).entries()).map(([id, name]) => ({ v: id, l: name })),
  ];
  const disc = videos
    .filter((v) => v.gap != null && v.gap >= threshold && (client === "all" || v.clientId === client))
    .map((v) => ({ ref: v.ref, clientObj: v.clientObj, ai: v.aiGrade, human: v.humanGrade, gap: v.gap as number, model: v.aiModel || "—" }));

  return (
    <div style={{ height: "100%", overflow: "auto", background: "var(--bg)" }}>
      <div style={{ maxWidth: 1280, margin: "0 auto", padding: "24px 28px 60px" }}>
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, marginBottom: 22, flexWrap: "wrap" }}>
          <div>
            <div className="label" style={{ marginBottom: 6 }}>{t("role.admin")}</div>
            <h1 style={{ fontSize: 26, letterSpacing: "-0.02em" }}>{t("dash.title")}</h1>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <Select value={client} onChange={setClient} options={clientOpts} icon="filter" />
          </div>
        </div>

        <Block title={t("dash.pipeline")} icon="layers">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 1, background: "var(--line)", border: "1px solid var(--line)", borderRadius: 6, overflow: "hidden" }}>
            {pipeline.map((p, i) => {
              const tone = p.tone === "red" ? "var(--red)" : p.tone === "amber" ? "var(--amber)" : p.tone === "green" ? "var(--green)" : p.tone === "accent" ? "var(--accent)" : "var(--ink)";
              return (
                <button key={p.key} style={{ background: "var(--panel)", border: "none", textAlign: "left", padding: "14px 14px 16px", cursor: "pointer", position: "relative", transition: "background .12s" }} onMouseEnter={(e) => (e.currentTarget.style.background = "var(--panel-2)")} onMouseLeave={(e) => (e.currentTarget.style.background = "var(--panel)")}>
                  {i > 0 && <Ico name="chevR" size={13} stroke="var(--line-strong)" style={{ position: "absolute", left: -7, top: 20 }} />}
                  <div className="mono tnum" style={{ fontSize: 30, fontWeight: 600, color: tone, lineHeight: 1 }}>{p.count}</div>
                  <div style={{ fontSize: 12, color: "var(--ink-2)", marginTop: 7, display: "flex", alignItems: "center", gap: 5 }}>
                    {p.tone === "red" && <span style={{ width: 6, height: 6, borderRadius: 99, background: "var(--red)" }} />}
                    {p.label}
                  </div>
                </button>
              );
            })}
          </div>
        </Block>

        <div style={{ display: "grid", gridTemplateColumns: "1.45fr 1fr", gap: 18, alignItems: "start" }}>
          <Block
            title={t("dash.disc")}
            icon="activity"
            aside={
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span className="label">{t("dash.discsub")}</span>
                <div style={{ display: "flex", alignItems: "center", gap: 6, background: "var(--panel-3)", borderRadius: 4, padding: "3px 8px" }}>
                  <input type="range" min="1" max="5" step="0.5" value={threshold} onChange={(e) => setThreshold(parseFloat(e.target.value))} style={{ width: 70, accentColor: "var(--accent)" }} />
                  <span className="mono tnum" style={{ fontSize: 12, fontWeight: 600, width: 22 }}>{threshold.toFixed(1)}</span>
                </div>
              </div>
            }
          >
            <div className="panel" style={{ overflow: "hidden" }}>
              <Row head cols="1.1fr 1.2fr 60px 64px 56px 1fr">
                {[t("queue.ref"), t("queue.client"), "AI", "Human", t("dash.gap"), `${t("dash.model")} · ${t("dash.prompt")}`].map((h, i) => (
                  <span key={i} className="label" style={{ textAlign: i >= 2 && i <= 4 ? "right" : "left" }}>{h}</span>
                ))}
              </Row>
              {disc.length === 0 ? (
                <EmptyInline icon="check" msg="No discrepancies above threshold" />
              ) : (
                disc.map((d, i) => (
                  <Row key={d.ref} cols="1.1fr 1.2fr 60px 64px 56px 1fr" last={i === disc.length - 1}>
                    <span className="mono" style={{ fontWeight: 600, fontSize: 12.5 }}>{d.ref}</span>
                    <ClientChip client={d.clientObj} />
                    <span style={{ textAlign: "right" }}><Grade value={d.ai} size={12.5} muted /></span>
                    <span style={{ textAlign: "right" }}><Grade value={d.human} size={12.5} muted /></span>
                    <span style={{ textAlign: "right" }} className="mono tnum">
                      <span style={{ fontWeight: 700, color: d.gap >= 3 ? "var(--red)" : "var(--amber)", fontSize: 13 }}>{d.gap.toFixed(1)}</span>
                    </span>
                    <span className="mono" style={{ fontSize: 10.5, color: "var(--ink-3)" }}>{d.model}</span>
                  </Row>
                ))
              )}
            </div>
            <p style={{ fontSize: 11.5, color: "var(--ink-4)", marginTop: 8, display: "flex", alignItems: "center", gap: 6 }}>
              <Ico name="zap" size={12} /> This table is the prompt-tuning feed — large gaps point to model or prompt regressions.
            </p>
          </Block>

          <Block title={t("dash.cost")} icon="dollar">
            <div className="panel">
              <EmptyInline icon="dollar" msg="Per-client cost rollup has no API endpoint yet." />
            </div>
          </Block>
        </div>

        <Block title={t("dash.through")} icon="user">
          <div className="panel">
            <EmptyInline icon="user" msg="Reviewer throughput has no API endpoint yet." />
          </div>
        </Block>
      </div>
    </div>
  );
}

function Block({ title, icon, aside, children }: { title: string; icon: string; aside?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: 22 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <h2 style={{ fontSize: 13.5, display: "flex", alignItems: "center", gap: 8, fontWeight: 600, whiteSpace: "nowrap", flexShrink: 0 }}>
          <Ico name={icon} size={15} stroke="var(--ink-3)" /> {title}
        </h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

// Map raw VideoStatus -> StatusPill key.
const PILL_FOR: Record<string, string> = {
  done: "done",
  human_reviewed: "done",
  ai_reviewed: "ai_graded",
  frames_extracted: "processing",
  ingested: "processing",
  failed: "failed",
};

function StatusPill({ status, t }: { status: string; t: TFn }) {
  const map: Record<string, { l: string; c: string; bg: string }> = {
    done: { l: t("portal.reviewed"), c: "var(--green)", bg: "var(--green-bg)" },
    in_review: { l: t("portal.inreview"), c: "var(--amber)", bg: "var(--amber-bg)" },
    ai_graded: { l: "AI graded", c: "var(--accent)", bg: "var(--accent-2)" },
    processing: { l: t("portal.processing"), c: "var(--ink-3)", bg: "var(--panel-3)" },
    failed: { l: "Failed", c: "var(--red)", bg: "var(--red-bg)" },
  };
  const m = map[status] || map.processing;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 600, color: m.c, background: m.bg, padding: "3px 8px", borderRadius: 99, width: "fit-content" }}>
      <span style={{ width: 5, height: 5, borderRadius: 99, background: m.c }} />{m.l}
    </span>
  );
}

function VideosView({ t, onOpenReview }: { t: TFn; onOpenReview: (id: string) => void }) {
  const [q, setQ] = useState("");
  const board = useLive<BoardVideo[]>(() => api.boardVideos(), []);
  const rows = board.data.filter((v) => v.ref.toLowerCase().includes(q.toLowerCase()) || v.clientObj.name.toLowerCase().includes(q.toLowerCase()));
  return (
    <div style={{ height: "100%", overflow: "auto", background: "var(--bg)" }}>
      <div style={{ maxWidth: 1180, margin: "0 auto", padding: "24px 28px 60px" }}>
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: 18, gap: 16, flexWrap: "wrap" }}>
          <div>
            <div className="label" style={{ marginBottom: 6 }}>{t("role.admin")}</div>
            <h1 style={{ fontSize: 24, letterSpacing: "-0.02em" }}>{t("nav.videos")}</h1>
          </div>
          <SearchBox q={q} setQ={setQ} t={t} />
        </div>
        <div className="panel" style={{ overflow: "hidden" }}>
          <Row head cols="50px 1.1fr 1.3fr 90px 110px 80px 80px">
            {["", t("queue.ref"), t("queue.client"), t("queue.scene"), t("portal.status"), "AI", ""].map((h, i) => (
              <span key={i} className="label" style={{ textAlign: i === 5 ? "right" : "left" }}>{h}</span>
            ))}
          </Row>
          {rows.length === 0 ? (
            <EmptyInline icon="film" msg="No videos yet — register a source or run the demo." />
          ) : rows.map((v, i) => (
            <Row key={v.id} cols="50px 1.1fr 1.3fr 90px 110px 80px 80px" last={i === rows.length - 1} onClick={() => onOpenReview(v.id)}>
              <FrameThumb frame={{ hue: sceneOf(v.scene).hue }} style={{ width: 40, height: 24 }} showHud={false} />
              <span className="mono" style={{ fontWeight: 600, fontSize: 12.5 }}>{v.ref}</span>
              <ClientChip client={v.clientObj} />
              <span className="mono" style={{ fontSize: 11, color: "var(--ink-2)" }}>{sceneOf(v.scene).label}</span>
              <StatusPill status={PILL_FOR[v.status] || "processing"} t={t} />
              <span style={{ textAlign: "right" }}><Grade value={v.aiGrade} size={12.5} /></span>
              <span style={{ display: "flex", alignItems: "center", gap: 5, justifyContent: "flex-end", color: "var(--ink-3)", fontSize: 11 }}>
                <Ico name="eye" size={13} /> view
              </span>
            </Row>
          ))}
        </div>
      </div>
    </div>
  );
}

function JobsView({ t }: { t: TFn }) {
  // No job-list endpoint exists; surface the live queue-health counts instead.
  const metrics = useLive<Metrics | null>(() => api.adminMetrics(), null);
  const m = metrics.data;
  const cards: { label: string; value: number; tone: string }[] = [
    { label: "Queued", value: m?.queue_depth ?? 0, tone: "var(--ink)" },
    { label: "Running", value: m?.running_jobs ?? 0, tone: "var(--accent)" },
    { label: "Dead", value: m?.dead_jobs ?? 0, tone: "var(--red)" },
    { label: "Webhook failures", value: m?.webhook_failures ?? 0, tone: "var(--amber)" },
  ];
  return (
    <div style={{ height: "100%", overflow: "auto", background: "var(--bg)" }}>
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "24px 28px 60px" }}>
        <div style={{ marginBottom: 18 }}>
          <div className="label" style={{ marginBottom: 6 }}>{t("role.admin")}</div>
          <h1 style={{ fontSize: 24, letterSpacing: "-0.02em" }}>{t("nav.jobs")}</h1>
          <p style={{ color: "var(--ink-3)", fontSize: 13, marginTop: 4 }}>Processing-queue health from <span className="mono">/admin/metrics</span>.</p>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 1, background: "var(--line)", border: "1px solid var(--line)", borderRadius: 6, overflow: "hidden" }}>
          {cards.map((c) => (
            <div key={c.label} style={{ background: "var(--panel)", padding: "16px 16px 18px" }}>
              <div className="mono tnum" style={{ fontSize: 30, fontWeight: 600, color: c.tone, lineHeight: 1 }}>{c.value}</div>
              <div style={{ fontSize: 12, color: "var(--ink-2)", marginTop: 7 }}>{c.label}</div>
            </div>
          ))}
        </div>
        <p style={{ fontSize: 11.5, color: "var(--ink-4)", marginTop: 12, display: "flex", alignItems: "center", gap: 6 }}>
          <Ico name="layers" size={12} /> A per-job list (with retry) needs a jobs API endpoint — not built yet.
        </p>
      </div>
    </div>
  );
}
