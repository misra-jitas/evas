// Client Portal (read-only, tenancy-isolated). No costs, reviewer names,
// model/prompt, or confidence. The video list is wired to GET /portal/videos;
// detail + exports keep the prototype's branded mock layout.
import { useState } from "react";
import { api, useLive } from "../api";
import { Btn, FrameThumb, Grade, Ico, Row } from "../components";
import { D, sceneOf } from "../data";
import type { Client, PortalVideo, TFn } from "../types";

export function PortalScreen({ t, sub, portalClient }: { t: TFn; sub: string | null; portalClient: Client }) {
  const live = useLive<PortalVideo[]>(() => api.portalVideos(), []);
  const [openRef, setOpenRef] = useState<string | null>(null);

  if (sub === "exports") return <ExportsView t={t} client={portalClient} />;

  const videos = live.data;
  const open = openRef ? videos.find((v) => v.ref === openRef) : null;

  return (
    <div style={{ height: "100%", overflow: "auto", background: "var(--bg)" }}>
      <div style={{ maxWidth: 1080, margin: "0 auto", padding: "26px 28px 60px" }}>
        {!open ? (
          <>
            <div style={{ marginBottom: 20 }}>
              <div className="label" style={{ marginBottom: 6 }}>{portalClient.name}</div>
              <h1 style={{ fontSize: 26, letterSpacing: "-0.02em" }}>{t("portal.title")}</h1>
              <p style={{ color: "var(--ink-3)", fontSize: 13, marginTop: 4 }}>
                <span className="mono tnum" style={{ color: "var(--ink)", fontWeight: 600 }}>{videos.length}</span> videos ·
                <span className="mono tnum" style={{ color: "var(--green)", fontWeight: 600 }}> {videos.filter((v) => v.status === "reviewed").length}</span> reviewed
              </p>
            </div>
            <div className="panel" style={{ overflow: "hidden", boxShadow: "var(--shadow-1)" }}>
              <Row head cols="56px 1.2fr 1fr 150px 90px 40px">
                {["", t("queue.ref"), t("portal.uploaded"), t("portal.status"), t("portal.grade"), ""].map((h, i) => (
                  <span key={i} className="label" style={{ textAlign: i === 4 ? "right" : "left" }}>{h}</span>
                ))}
              </Row>
              {videos.map((v, i) => {
                const reviewed = v.status === "reviewed";
                return (
                  <Row key={v.ref} cols="56px 1.2fr 1fr 150px 90px 40px" last={i === videos.length - 1} onClick={reviewed ? () => setOpenRef(v.ref) : undefined} style={{ cursor: reviewed ? "pointer" : "default", opacity: reviewed ? 1 : 0.82 }}>
                    <FrameThumb frame={{ hue: sceneOf(v.scene).hue }} style={{ width: 46, height: 28 }} showHud={false} />
                    <span className="mono" style={{ fontWeight: 600, fontSize: 13 }}>{v.ref}</span>
                    <span className="mono" style={{ fontSize: 12, color: "var(--ink-2)" }}>{v.uploaded}</span>
                    <PortalStatus status={v.status} t={t} />
                    <span style={{ textAlign: "right" }}><Grade value={v.grade} size={14} /></span>
                    <span style={{ color: "var(--ink-4)" }}>{reviewed && <Ico name="chevR" size={15} />}</span>
                  </Row>
                );
              })}
            </div>
          </>
        ) : (
          <PortalDetail v={open} t={t} onBack={() => setOpenRef(null)} />
        )}
      </div>
    </div>
  );
}

function PortalDetail({ v, t, onBack }: { v: PortalVideo; t: TFn; onBack: () => void }) {
  const scene = sceneOf(v.scene);
  const results = D.CHECKLIST.items.map((it, i) => ({ label: it.label, value: it.expect, ok: i !== 2 }));
  const notable = [
    { tc: "00:12:08", note: "Activity clearly framed; hands and object both visible.", hue: scene.hue },
    { tc: "00:31:20", note: "Brief occlusion — flagged then cleared by reviewer.", hue: scene.hue + 6 },
    { tc: "00:47:14", note: "Bystander visible; no PII concern after review.", hue: scene.hue - 4 },
  ];
  return (
    <div className="fade-in">
      <Btn kind="ghost" size="sm" icon="arrowL" onClick={onBack} style={{ marginBottom: 14, marginLeft: -6 }}>{t("portal.title")}</Btn>
      <div style={{ display: "grid", gridTemplateColumns: "1.1fr 1fr", gap: 22, alignItems: "start" }}>
        <div>
          <FrameThumb frame={{ hue: scene.hue, timecode: "00:00:00", flagged: false }} large style={{ width: "100%", aspectRatio: "16/9", boxShadow: "var(--shadow-2)" }} />
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 12 }}>
            <h1 className="mono" style={{ fontSize: 22, whiteSpace: "nowrap" }}>{v.ref}</h1>
            <span className="label" style={{ background: "var(--panel-3)", padding: "3px 7px", borderRadius: 3 }}>{scene.label}</span>
          </div>
          <div className="panel" style={{ marginTop: 14, padding: 16, display: "flex", alignItems: "center", gap: 18 }}>
            <div>
              <div className="label" style={{ marginBottom: 4 }}>{t("portal.grade")}</div>
              <Grade value={v.grade} size={42} />
            </div>
            <div style={{ width: 1, alignSelf: "stretch", background: "var(--line)" }} />
            <div style={{ flex: 1 }}>
              <div className="label" style={{ marginBottom: 4 }}>Summary</div>
              <p style={{ margin: 0, fontSize: 13, color: "var(--ink-2)", lineHeight: 1.55 }}>{scene.act}. High-quality clip — activity clearly framed throughout, no privacy concerns after review.</p>
            </div>
          </div>
        </div>

        <div>
          <div className="label" style={{ marginBottom: 8 }}>{t("portal.results")}</div>
          <div className="panel" style={{ overflow: "hidden" }}>
            {results.map((r, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 13px", borderBottom: i < results.length - 1 ? "1px solid var(--line-2)" : "none" }}>
                <span style={{ fontSize: 13 }}>{r.label}</span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 600, color: r.ok ? "var(--green)" : "var(--amber)" }}>
                  <Ico name={r.ok ? "check" : "alert"} size={14} /> {r.value}
                </span>
              </div>
            ))}
          </div>

          <div className="label" style={{ margin: "18px 0 8px" }}>{t("portal.notable")}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {notable.map((n, i) => (
              <div key={i} className="panel" style={{ display: "flex", gap: 12, padding: 10, alignItems: "center" }}>
                <FrameThumb frame={{ hue: n.hue, timecode: n.tc, flagged: false }} style={{ width: 86, height: 50, flexShrink: 0 }} showHud={false} />
                <div style={{ minWidth: 0 }}>
                  <span className="mono" style={{ fontSize: 11, color: "var(--accent)", fontWeight: 600 }}>{n.tc}</span>
                  <p style={{ margin: "3px 0 0", fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.45 }}>{n.note}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function PortalStatus({ status, t }: { status: PortalVideo["status"]; t: TFn }) {
  const map: Record<string, { l: string; c: string; bg: string }> = {
    reviewed: { l: t("portal.reviewed"), c: "var(--green)", bg: "var(--green-bg)" },
    in_review: { l: t("portal.inreview"), c: "var(--amber)", bg: "var(--amber-bg)" },
    processing: { l: t("portal.processing"), c: "var(--ink-3)", bg: "var(--panel-3)" },
  };
  const m = map[status];
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11.5, fontWeight: 600, color: m.c, background: m.bg, padding: "4px 10px", borderRadius: 99, width: "fit-content" }}>
      <span style={{ width: 6, height: 6, borderRadius: 99, background: m.c }} className={status === "processing" ? "rec-dot" : ""} />{m.l}
    </span>
  );
}

function ExportsView({ t, client }: { t: TFn; client: Client }) {
  const [from, setFrom] = useState("2026-06-01");
  const [to, setTo] = useState("2026-06-07");
  const [done, setDone] = useState<string | null>(null);
  function exp(kind: string) {
    setDone(kind);
    setTimeout(() => setDone(null), 2200);
  }
  return (
    <div style={{ height: "100%", overflow: "auto", background: "var(--bg)" }}>
      <div style={{ maxWidth: 720, margin: "0 auto", padding: "26px 28px 60px" }}>
        <div style={{ marginBottom: 22 }}>
          <div className="label" style={{ marginBottom: 6 }}>{client.name}</div>
          <h1 style={{ fontSize: 24, letterSpacing: "-0.02em" }}>{t("nav.exports")}</h1>
        </div>
        <div className="panel" style={{ padding: 18, marginBottom: 16 }}>
          <div className="label" style={{ marginBottom: 10 }}>{t("portal.range")}</div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 18 }}>
            <DateField value={from} onChange={setFrom} />
            <span style={{ color: "var(--ink-4)" }}>→</span>
            <DateField value={to} onChange={setTo} />
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Btn kind="default" icon="download" onClick={() => exp("csv")}>{t("portal.export")}</Btn>
            <Btn kind="default" icon="download" onClick={() => exp("billing")}>{t("portal.billing")}</Btn>
          </div>
          {done && (
            <div className="fade-in" style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, color: "var(--green)" }}>
              <Ico name="check" size={15} /> {done === "csv" ? "findings.csv" : "billing-jun-2026.pdf"} generated · download started
            </div>
          )}
        </div>
        <p style={{ fontSize: 12, color: "var(--ink-4)", lineHeight: 1.6 }}>
          Exports include final grades, checklist results and frame notes for your videos only. Internal data (costs, reviewer identity, model details) is never included.
        </p>
      </div>
    </div>
  );
}

function DateField({ value, onChange }: { value: string; onChange: (s: string) => void }) {
  return (
    <input type="date" value={value} onChange={(e) => onChange(e.target.value)} style={{ padding: "8px 11px", borderRadius: 4, border: "1px solid var(--line-strong)", background: "var(--panel-2)", fontSize: 13, fontFamily: '"IBM Plex Mono", monospace', color: "var(--ink)", outline: "none" }} />
  );
}
