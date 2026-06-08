// Ops Dashboard (admin): pipeline · discrepancy · throughput · cost, plus
// /videos and /jobs sub-views. The pipeline "failed" card is overlaid from the
// live GET /admin/metrics (dead_jobs); the rest use mock aggregates (no single
// matching endpoint — gaps stay mock per scope).
import { useState } from "react";
import { api, useLive } from "../api";
import {
  Avatar,
  BarCell,
  Btn,
  ClientChip,
  EmptyInline,
  FrameThumb,
  Grade,
  Ico,
  Row,
  SearchBox,
  Select,
  Spark,
} from "../components";
import { D, sceneOf } from "../data";
import type { TFn } from "../types";

interface Metrics {
  dead_jobs: number;
  queue_depth: number;
  running_jobs: number;
  webhook_failures: number;
}

export function DashboardScreen({ t, sub, onOpenReview }: { t: TFn; sub: string | null; onOpenReview: (id: string) => void }) {
  const [threshold, setThreshold] = useState(2);
  const [client, setClient] = useState("all");
  const metrics = useLive<Metrics | null>(() => api.adminMetrics(), null);

  if (sub === "videos") return <VideosView t={t} onOpenReview={onOpenReview} />;
  if (sub === "jobs") return <JobsView t={t} />;

  const disc = D.DISCREPANCY.filter((d) => d.gap >= threshold && (client === "all" || d.client.id === client));
  const pipeline = D.PIPELINE.map((p) => (p.key === "failed" && metrics.live && metrics.data ? { ...p, count: metrics.data.dead_jobs } : p));

  return (
    <div style={{ height: "100%", overflow: "auto", background: "var(--bg)" }}>
      <div style={{ maxWidth: 1280, margin: "0 auto", padding: "24px 28px 60px" }}>
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, marginBottom: 22, flexWrap: "wrap" }}>
          <div>
            <div className="label" style={{ marginBottom: 6 }}>{t("role.admin")}</div>
            <h1 style={{ fontSize: 26, letterSpacing: "-0.02em" }}>{t("dash.title")}</h1>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <Select value={client} onChange={setClient} options={[{ v: "all", l: t("common.all") }, ...D.CLIENTS.map((c) => ({ v: c.id, l: c.name }))]} icon="filter" />
            <Select value="jun" onChange={() => {}} options={[{ v: "jun", l: "Jun 2026" }, { v: "may", l: "May 2026" }]} icon="clock" />
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
                    <ClientChip client={d.client} />
                    <span style={{ textAlign: "right" }}><Grade value={d.ai} size={12.5} muted /></span>
                    <span style={{ textAlign: "right" }}><Grade value={d.human} size={12.5} muted /></span>
                    <span style={{ textAlign: "right" }} className="mono tnum">
                      <span style={{ fontWeight: 700, color: d.gap >= 3 ? "var(--red)" : "var(--amber)", fontSize: 13 }}>{d.gap.toFixed(1)}</span>
                    </span>
                    <span className="mono" style={{ fontSize: 10.5, color: "var(--ink-3)" }}>{d.model} · {d.prompt}</span>
                  </Row>
                ))
              )}
            </div>
            <p style={{ fontSize: 11.5, color: "var(--ink-4)", marginTop: 8, display: "flex", alignItems: "center", gap: 6 }}>
              <Ico name="zap" size={12} /> This table is the prompt-tuning feed — large gaps point to model or prompt regressions.
            </p>
          </Block>

          <Block title={t("dash.cost")} icon="dollar">
            <div className="panel" style={{ overflow: "hidden" }}>
              {D.COST.map((c, i) => (
                <div key={c.client} style={{ padding: "11px 14px", borderBottom: i < D.COST.length - 1 ? "1px solid var(--line-2)" : "none" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <ClientChip client={c.clientObj} />
                    <span className="mono tnum" style={{ fontWeight: 600, fontSize: 14 }}>${c.cost.toFixed(2)}</span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 7 }}>
                    <span className="mono" style={{ fontSize: 10.5, color: "var(--ink-3)" }}>{c.videos} {t("dash.videos")} · {(c.tokens / 1e6).toFixed(2)}M {t("dash.tokens")}</span>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span className="mono" style={{ fontSize: 10, color: "var(--ink-4)" }}>{t("dash.percost")}</span>
                      <Spark data={c.trend} tone={c.trend[c.trend.length - 1] < c.trend[0] ? "var(--green)" : "var(--red)"} />
                    </div>
                  </div>
                </div>
              ))}
              <div style={{ padding: "11px 14px", background: "var(--panel-2)", display: "flex", justifyContent: "space-between" }}>
                <span className="label" style={{ alignSelf: "center" }}>Total MTD</span>
                <span className="mono tnum" style={{ fontWeight: 700, fontSize: 15 }}>${D.COST.reduce((s, c) => s + c.cost, 0).toFixed(2)}</span>
              </div>
            </div>
          </Block>
        </div>

        <Block title={t("dash.through")} icon="user">
          <div className="panel" style={{ overflow: "hidden" }}>
            <Row head cols="1.4fr 1fr 1fr 1.2fr 1.2fr">
              {["Reviewer", `Reviews ${t("dash.perday")}`, t("dash.avgmin"), t("dash.override"), t("dash.qa")].map((h, i) => (
                <span key={i} className="label">{h}</span>
              ))}
            </Row>
            {D.THROUGHPUT.map((r, i) => (
              <Row key={r.r} cols="1.4fr 1fr 1fr 1.2fr 1.2fr" last={i === D.THROUGHPUT.length - 1}>
                <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Avatar initials={r.reviewer.initials} /> <span style={{ fontSize: 13 }}>{r.reviewer.name}</span>
                </span>
                <span className="mono tnum" style={{ fontWeight: 600 }}>{r.perDay}</span>
                <span className="mono tnum" style={{ color: "var(--ink-2)" }}>{r.avgMin.toFixed(1)}</span>
                <BarCell v={r.overrideRate} max={0.3} tone="var(--amber)" fmt={(x) => Math.round(x * 100) + "%"} />
                <BarCell v={r.qaAgree} max={1} tone="var(--green)" fmt={(x) => Math.round(x * 100) + "%"} />
              </Row>
            ))}
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
  const all = D.QUEUE.concat(D.QUEUE.map((v) => ({ ...v, id: v.ref + "-b", ref: v.ref.replace("EGO-248", "EGO-247") })));
  const rows = all.filter((v) => v.ref.toLowerCase().includes(q.toLowerCase()) || v.client.name.toLowerCase().includes(q.toLowerCase()));
  const statusFor = (i: number) => ["done", "in_review", "done", "ai_graded", "done", "in_review"][i % 6];
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
          {rows.map((v, i) => (
            <Row key={v.id} cols="50px 1.1fr 1.3fr 90px 110px 80px 80px" last={i === rows.length - 1} onClick={() => onOpenReview(v.ref.replace("-b", "").replace("EGO-247", "EGO-248"))}>
              <FrameThumb frame={{ hue: sceneOf(v.scene).hue }} style={{ width: 40, height: 24 }} showHud={false} />
              <span className="mono" style={{ fontWeight: 600, fontSize: 12.5 }}>{v.ref}</span>
              <ClientChip client={v.client} />
              <span className="mono" style={{ fontSize: 11, color: "var(--ink-2)" }}>{v.sceneLabel}</span>
              <StatusPill status={statusFor(i)} t={t} />
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
  const [jobs, setJobs] = useState(D.JOBS);
  const [retrying, setRetrying] = useState<string | null>(null);
  function retry(id: string) {
    setRetrying(id);
    setTimeout(() => {
      setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, status: "running", attempts: j.attempts + 1, lastError: "" } : j)));
      setRetrying(null);
    }, 900);
  }
  const tones: Record<string, string> = { failed: "var(--red)", dead: "var(--red)", running: "var(--accent)" };
  return (
    <div style={{ height: "100%", overflow: "auto", background: "var(--bg)" }}>
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "24px 28px 60px" }}>
        <div style={{ marginBottom: 18 }}>
          <div className="label" style={{ marginBottom: 6 }}>{t("role.admin")}</div>
          <h1 style={{ fontSize: 24, letterSpacing: "-0.02em" }}>{t("nav.jobs")}</h1>
          <p style={{ color: "var(--ink-3)", fontSize: 13, marginTop: 4 }}>Processing pipeline — failed &amp; dead jobs need attention.</p>
        </div>
        <div className="panel" style={{ overflow: "hidden" }}>
          <Row head cols="90px 1fr 1fr 1.6fr 60px 80px 92px">
            {["Job", t("queue.ref"), "Stage", "Last error", "Try", "Status", ""].map((h, i) => (
              <span key={i} className="label">{h}</span>
            ))}
          </Row>
          {jobs.map((j, i) => (
            <Row key={j.id} cols="90px 1fr 1fr 1.6fr 60px 80px 92px" last={i === jobs.length - 1}>
              <span className="mono" style={{ fontSize: 11.5, color: "var(--ink-3)" }}>{j.id}</span>
              <span className="mono" style={{ fontSize: 12.5, fontWeight: 600 }}>{j.ref}</span>
              <span className="mono" style={{ fontSize: 11.5, color: "var(--ink-2)" }}>{j.stage}</span>
              <span style={{ fontSize: 11.5, color: j.lastError ? "var(--red)" : "var(--ink-4)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontFamily: j.lastError ? '"IBM Plex Mono", monospace' : "inherit" }}>{j.lastError || "—"}</span>
              <span className="mono tnum" style={{ fontSize: 12, color: j.attempts >= 5 ? "var(--red)" : "var(--ink-2)" }}>{j.attempts}×</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11.5, fontWeight: 600, color: tones[j.status], textTransform: "capitalize" }}>
                <span style={{ width: 6, height: 6, borderRadius: 99, background: tones[j.status] }} className={j.status === "running" ? "rec-dot" : ""} />{j.status}
              </span>
              <span style={{ textAlign: "right" }}>
                {(j.status === "failed" || j.status === "dead") && (
                  <Btn kind="default" size="sm" icon="refresh" onClick={() => retry(j.id)} disabled={retrying === j.id}>
                    {retrying === j.id ? "…" : t("common.retry")}
                  </Btn>
                )}
              </span>
            </Row>
          ))}
        </div>
      </div>
    </div>
  );
}
