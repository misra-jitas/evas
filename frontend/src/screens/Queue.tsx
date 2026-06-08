// Reviewer Workbench: Queue screen. Priority-sorted assigned reviews + Start next.
import { useEffect, useMemo, useState } from "react";
import { Btn, ClientChip, FrameThumb, Grade, Ico, PriorityBadge } from "../components";
import { D, sceneOf } from "../data";
import type { Priority, TFn } from "../types";

export interface SessionState {
  reviewedToday: number;
  target: number;
  streak: number;
  agreeSum: number;
  agreeCount: number;
}

const ORDER: Record<Priority, number> = { rush: 0, high: 1, normal: 2 };

function ago(m: number): string {
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m ago`;
}

const COLS = "78px 96px 1fr 150px 86px 70px 78px 110px";

export function QueueScreen({ t, onOpen, session }: { t: TFn; onOpen: (id: string) => void; session: SessionState }) {
  const [loading, setLoading] = useState(true);
  const [hover, setHover] = useState<string | null>(null);

  useEffect(() => {
    const id = setTimeout(() => setLoading(false), 620);
    return () => clearTimeout(id);
  }, []);

  const queue = useMemo(
    () => [...D.QUEUE].sort((a, b) => ORDER[a.priority] - ORDER[b.priority] || b.assignedMins - a.assignedMins),
    [],
  );
  const next = queue[0];
  const rushCount = queue.filter((q) => q.priority === "rush").length;
  const totalFlagged = queue.reduce((s, q) => s + q.flaggedCount, 0);

  return (
    <div style={{ height: "100%", overflow: "auto", background: "var(--bg)" }}>
      <div style={{ maxWidth: 1180, margin: "0 auto", padding: "26px 28px 60px" }}>
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 20, marginBottom: 20, flexWrap: "wrap" }}>
          <div>
            <div className="label" style={{ marginBottom: 6 }}>{t("role.reviewer")}</div>
            <h1 style={{ fontSize: 26, letterSpacing: "-0.02em" }}>{t("queue.title")}</h1>
            <div style={{ color: "var(--ink-3)", fontSize: 13, marginTop: 4 }}>
              <span className="mono tnum" style={{ color: "var(--ink)", fontWeight: 600 }}>{queue.length}</span> {t("queue.assigned")}
              <span style={{ margin: "0 8px", color: "var(--line-strong)" }}>·</span>
              <span className="mono tnum" style={{ color: "var(--red)", fontWeight: 600 }}>{rushCount}</span> rush
              <span style={{ margin: "0 8px", color: "var(--line-strong)" }}>·</span>
              <span className="mono tnum" style={{ color: "var(--amber)", fontWeight: 600 }}>{totalFlagged}</span> flagged frames
            </div>
          </div>
          <Btn kind="primary" size="lg" icon="zap" onClick={() => onOpen(next.id)} style={{ boxShadow: "var(--shadow-2)" }}>
            {t("queue.startnext")}
            <span className="mono" style={{ fontSize: 11, opacity: 0.7, marginLeft: 8, padding: "1px 5px", border: "1px solid currentColor", borderRadius: 3 }}>{next?.ref}</span>
          </Btn>
        </div>

        {session && (
          <div className="panel" style={{ display: "flex", alignItems: "center", gap: 16, padding: "12px 16px", marginBottom: 16 }}>
            <span style={{ width: 34, height: 34, borderRadius: 7, flexShrink: 0, display: "grid", placeItems: "center", background: "var(--green-bg)", color: "var(--green)" }}>
              <Ico name="check" size={17} sw={2.4} />
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <span className="mono tnum" style={{ fontSize: 16, fontWeight: 600 }}>{session.reviewedToday}</span>
                <span style={{ fontSize: 12.5, color: "var(--ink-3)" }}>/ {session.target} reviewed today</span>
                {session.streak >= 3 && (
                  <span style={{ marginLeft: 4, display: "inline-flex", alignItems: "center", gap: 3, fontSize: 11.5, color: "var(--amber)", fontWeight: 600 }}>
                    <Ico name="bolt" size={12} fill="var(--amber)" stroke="none" /> {session.streak} streak
                  </span>
                )}
              </div>
              <div style={{ marginTop: 7, height: 6, borderRadius: 99, background: "var(--panel-3)", overflow: "hidden", border: "1px solid var(--line)" }}>
                <div style={{ width: `${Math.min(100, (session.reviewedToday / session.target) * 100)}%`, height: "100%", background: "var(--green)", transition: "width .5s cubic-bezier(.2,.6,.2,1)" }} />
              </div>
            </div>
            <span style={{ fontSize: 11.5, color: "var(--ink-4)", maxWidth: 180, textAlign: "right", lineHeight: 1.4 }}>
              Rhythm over speed — the queue waits for you, not the other way around.
            </span>
          </div>
        )}

        <div className="panel" style={{ overflow: "hidden", boxShadow: "var(--shadow-1)" }}>
          <div style={{ display: "grid", gridTemplateColumns: COLS, gap: 12, alignItems: "center", padding: "9px 16px", borderBottom: "1px solid var(--line)", background: "var(--panel-2)" }}>
            {[t("queue.priority"), "", t("queue.ref"), t("queue.client"), t("queue.scene"), t("queue.ai"), t("queue.flagged"), t("queue.assignedat")].map((h, i) => (
              <div key={i} className="label" style={{ textAlign: i === 5 || i === 6 ? "right" : "left" }}>{h}</div>
            ))}
          </div>

          {loading
            ? Array.from({ length: 6 }).map((_, i) => (
                <div key={i} style={{ display: "grid", gridTemplateColumns: COLS, gap: 12, alignItems: "center", padding: "12px 16px", borderBottom: "1px solid var(--line-2)" }}>
                  <div className="skel" style={{ height: 16, width: 48 }} />
                  <div className="skel" style={{ height: 34, width: 60, borderRadius: 4 }} />
                  <div className="skel" style={{ height: 14, width: "70%" }} />
                  <div className="skel" style={{ height: 14, width: "80%" }} />
                  <div className="skel" style={{ height: 14, width: 50 }} />
                  <div className="skel" style={{ height: 14, width: 28, marginLeft: "auto" }} />
                  <div className="skel" style={{ height: 14, width: 28, marginLeft: "auto" }} />
                  <div className="skel" style={{ height: 14, width: 70 }} />
                </div>
              ))
            : queue.map((q, i) => (
                <div
                  key={q.id}
                  className="fade-in"
                  onClick={() => onOpen(q.id)}
                  onMouseEnter={() => setHover(q.id)}
                  onMouseLeave={() => setHover(null)}
                  style={{ display: "grid", gridTemplateColumns: COLS, gap: 12, alignItems: "center", padding: "11px 16px", cursor: "pointer", borderBottom: i < queue.length - 1 ? "1px solid var(--line-2)" : "none", background: hover === q.id ? "var(--panel-2)" : "transparent", animationDelay: `${i * 28}ms`, position: "relative" }}
                >
                  {q.priority === "rush" && <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: "var(--red)" }} />}
                  <div><PriorityBadge p={q.priority} /></div>
                  <FrameThumb frame={{ hue: sceneOf(q.scene).hue, timecode: "00:00:00", flagged: false }} style={{ width: 60, height: 34 }} showHud={false} />
                  <div style={{ minWidth: 0 }}>
                    <div className="mono" style={{ fontSize: 13, fontWeight: 600, letterSpacing: "-0.01em" }}>{q.ref}</div>
                    <div style={{ fontSize: 11, color: "var(--ink-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{q.duration} · {q.frameCount} {t("queue.frames").toLowerCase()}</div>
                  </div>
                  <ClientChip client={q.client} />
                  <div className="mono" style={{ fontSize: 11, color: "var(--ink-2)", letterSpacing: "0.04em" }}>{q.sceneLabel}</div>
                  <div style={{ textAlign: "right" }}><Grade value={q.aiGrade} /></div>
                  <div style={{ textAlign: "right" }}>
                    {q.flaggedCount > 0 ? (
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: "var(--amber)" }}>
                        <Ico name="flag" size={12} fill="var(--amber)" stroke="none" />
                        <span className="mono tnum" style={{ fontSize: 12, fontWeight: 600 }}>{q.flaggedCount}</span>
                      </span>
                    ) : (
                      <span className="mono" style={{ color: "var(--ink-4)" }}>0</span>
                    )}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>{ago(q.assignedMins)}</span>
                    <span style={{ opacity: hover === q.id ? 1 : 0, transition: "opacity .12s", color: "var(--accent)" }}>
                      <Ico name="arrowR" size={15} />
                    </span>
                  </div>
                </div>
              ))}
        </div>

        <div style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 8, color: "var(--ink-4)", fontSize: 12 }}>
          <Ico name="zap" size={13} />
          Reviewers don't browse — they flow. Hit <kbd style={{ margin: "0 2px" }}>Start next</kbd> and clear the highest-priority clip.
        </div>
      </div>
    </div>
  );
}
