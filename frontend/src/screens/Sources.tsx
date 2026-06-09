// Sources (admin, first nav item): list with funnel bars, register modal, detail.
// List + Sync now are wired to the live API (GET /sources, POST /sources/{id}/sync);
// the register form is optimistic-local (live POST needs a real client UUID).
import { useEffect, useState } from "react";
import { api, useLive } from "../api";
import {
  Btn,
  ClientChip,
  Dotsep,
  EmptyState,
  Field,
  fieldInput,
  FrameThumb,
  FunnelBar,
  Grade,
  Ico,
  Kebab,
  Modal,
  Row,
  Segment,
  Select,
  StatusBadge,
  Toggle,
} from "../components";
import { D, sceneOf } from "../data";
import type { SelectOption } from "../components";
import type { BoardVideo, Source, TFn } from "../types";

// Raw VideoStatus -> StatusBadge token key.
const VIDEO_PILL: Record<string, string> = {
  done: "reviewed",
  human_reviewed: "reviewed",
  ai_reviewed: "ai_graded",
  frames_extracted: "processing",
  ingested: "processing",
  failed: "failed",
};

function ago(m: number): string {
  if (m === 0) return "just now";
  if (m < 60) return `${m}m ago`;
  if (m < 1440) return `${Math.floor(m / 60)}h ago`;
  return `${Math.floor(m / 1440)}d ago`;
}

export function SourcesScreen({
  t,
  sub,
  sourceId,
  onOpen,
  onOpenReview,
}: {
  t: TFn;
  sub: "list" | "detail";
  sourceId?: string;
  onOpen: (screen: "sources" | "detail", id?: string) => void;
  onOpenReview: (id: string) => void;
}) {
  const live = useLive<Source[]>(() => api.listSources(), []);
  const [sources, setSources] = useState<Source[]>(live.data);
  const [showReg, setShowReg] = useState(false);
  const [editing, setEditing] = useState<Source | null>(null);
  const [deleting, setDeleting] = useState<Source | null>(null);
  const [syncing, setSyncing] = useState<Record<string, boolean>>({});
  // Live clients for the register modal's picker (falls back to mock clients).
  const clientsLive = useLive<SelectOption[]>(
    () => api.listClients().then((rows) => rows.map((c) => ({ v: c.id, l: c.name }))),
    D.CLIENTS.map((c) => ({ v: c.id, l: c.name })),
  );

  useEffect(() => setSources(live.data), [live.data]);

  function syncNow(id: string) {
    setSyncing((s) => ({ ...s, [id]: true }));
    setSources((prev) => prev.map((x) => (x.id === id ? { ...x, status: "syncing" } : x)));
    api.syncSource(id).catch(() => {});
    setTimeout(() => {
      setSyncing((s) => ({ ...s, [id]: false }));
      setSources((prev) => prev.map((x) => (x.id === id ? { ...x, status: x.lastError ? "error" : "connected", lastSync: 0 } : x)));
      live.reload();
    }, 1600);
  }

  function register(form: { type: "s3" | "url"; uri: string; label: string; client: string; cred: string; autoSync: boolean }) {
    const c = D.clientOf(form.client);
    const ns: Source = {
      id: "src-" + Date.now(),
      type: form.type,
      label: form.label,
      uri: form.uri,
      cred: form.cred,
      client: form.client,
      clientObj: c,
      status: "syncing",
      autoSync: form.autoSync,
      lastSync: 0,
      total: 0,
      done: 0,
      inReview: 0,
      ingested: 0,
      toGo: 0,
      failed: 0,
    };
    setSources((prev) => [ns, ...prev]);
    setShowReg(false);
    // Persist for real (creates the source + kicks off a sync), then reconcile
    // with the server. On failure, surface the error on the optimistic row —
    // never fabricate discovery counts.
    api
      .createSource({ client_id: form.client, label: form.label, type: form.type, uri_prefix: form.uri, credential_ref: form.cred, auto_sync: form.autoSync })
      .then(() => setTimeout(() => live.reload(), 1800))
      .catch((e) => {
        setSources((prev) => prev.map((x) => (x.id === ns.id ? { ...x, status: "error", lastError: String(e?.message || e) } : x)));
      });
  }

  // Enable/disable a source, then reconcile with the server.
  function toggleEnabled(s: Source) {
    const enabled = s.status === "disabled";
    setSources((prev) => prev.map((x) => (x.id === s.id ? { ...x, status: enabled ? "connected" : "disabled" } : x)));
    api.updateSource(s.id, { enabled }).then(() => live.reload()).catch(() => live.reload());
  }

  // Delete a source (soft) after confirmation.
  function confirmDelete() {
    const s = deleting;
    if (!s) return;
    setDeleting(null);
    setSources((prev) => prev.filter((x) => x.id !== s.id));
    api.deleteSource(s.id).then(() => live.reload()).catch(() => live.reload());
  }

  // Save label/credential/auto-sync edits.
  function saveEdit(form: { label: string; cred: string; autoSync: boolean }) {
    const s = editing;
    if (!s) return;
    setEditing(null);
    setSources((prev) => prev.map((x) => (x.id === s.id ? { ...x, label: form.label, cred: form.cred, autoSync: form.autoSync } : x)));
    api
      .updateSource(s.id, { label: form.label, credential_ref: form.cred, auto_sync: form.autoSync })
      .then(() => live.reload())
      .catch(() => live.reload());
  }

  if (sub === "detail" && sourceId) {
    const src = sources.find((s) => s.id === sourceId) || sources[0];
    return <SourceDetail t={t} src={src} onBack={() => onOpen("sources")} onSync={() => syncNow(src.id)} onOpenReview={onOpenReview} />;
  }

  return (
    <div style={{ height: "100%", overflow: "auto", background: "var(--bg)" }}>
      <div style={{ maxWidth: 1180, margin: "0 auto", padding: "26px 28px 60px" }}>
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, marginBottom: 20, flexWrap: "wrap" }}>
          <div>
            <div className="label" style={{ marginBottom: 6 }}>{t("role.admin")}</div>
            <h1 style={{ fontSize: 26, letterSpacing: "-0.02em" }}>{t("src.title")}</h1>
            <p style={{ color: "var(--ink-3)", fontSize: 13, marginTop: 4 }}>{t("src.sub")}</p>
          </div>
          <Btn kind="primary" size="lg" icon="plus" onClick={() => setShowReg(true)} style={{ boxShadow: "var(--shadow-2)" }}>
            {t("src.register")}
          </Btn>
        </div>

        {sources.length === 0 ? (
          <EmptyState icon="database" title={t("src.empty")} sub={t("src.emptysub")} action={<Btn kind="primary" icon="plus" onClick={() => setShowReg(true)}>{t("src.register")}</Btn>} />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {sources.map((s, i) => (
              <div
                key={s.id}
                className="panel fade-in"
                onClick={() => onOpen("detail", s.id)}
                style={{ padding: 16, cursor: "pointer", boxShadow: "var(--shadow-1)", animationDelay: `${i * 30}ms`, opacity: s.status === "disabled" ? 0.72 : 1, transition: "border-color .12s" }}
                onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--line-strong)")}
                onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--line)")}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 13 }}>
                  <span style={{ width: 38, height: 38, borderRadius: 7, flexShrink: 0, display: "grid", placeItems: "center", background: "var(--panel-3)", border: "1px solid var(--line)", color: "var(--ink-2)" }}>
                    <Ico name={s.type === "s3" ? "database" : "link"} size={18} />
                  </span>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                      <span style={{ fontSize: 14.5, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }}>{s.label}</span>
                      <span className="mono" style={{ fontSize: 9.5, padding: "2px 6px", borderRadius: 3, background: "var(--panel-3)", color: "var(--ink-3)", letterSpacing: "0.04em", textTransform: "uppercase", flexShrink: 0 }}>{s.type}</span>
                    </div>
                    <div className="mono" style={{ fontSize: 11.5, color: "var(--ink-3)", marginTop: 3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.uri}</div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 14, flexShrink: 0 }}>
                    <ClientChip client={s.clientObj} />
                    <StatusBadge status={syncing[s.id] ? "syncing" : s.status} label={syncing[s.id] ? t("src.syncing") : t("src." + s.status)} />
                  </div>
                </div>
                <div style={{ marginTop: 14 }}>
                  {s.total === 0 ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--ink-4)", fontSize: 12.5, padding: "6px 0" }}>
                      <Ico name={s.status === "syncing" ? "refresh" : "clock"} size={14} style={s.status === "syncing" ? { animation: "evas-spin 1.4s linear infinite" } : undefined} />
                      {s.status === "syncing" ? "Scanning bucket — discovering videos…" : "Connected · no videos discovered yet"}
                    </div>
                  ) : (
                    <>
                      <FunnelBar src={s} />
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "2px 12px", marginTop: 9, fontSize: 11.5, color: "var(--ink-3)" }}>
                        <span><b className="mono tnum" style={{ color: "var(--ink)" }}>{s.total}</b> total</span>
                        <Dotsep /><span><b className="mono tnum" style={{ color: "var(--green)" }}>{s.done}</b> done</span>
                        <Dotsep /><span><b className="mono tnum" style={{ color: "var(--amber)" }}>{s.inReview}</b> in review</span>
                        <Dotsep /><span><b className="mono tnum" style={{ color: "var(--accent)" }}>{s.ingested}</b> ingested</span>
                        <Dotsep /><span><b className="mono tnum" style={{ color: "var(--ink-2)" }}>{s.toGo}</b> to ingest</span>
                        {s.failed > 0 && (<><Dotsep /><span><b className="mono tnum" style={{ color: "var(--red)" }}>{s.failed}</b> failed</span></>)}
                      </div>
                    </>
                  )}
                </div>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 14, paddingTop: 12, borderTop: "1px solid var(--line-2)" }} onClick={(e) => e.stopPropagation()}>
                  <span style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11.5, color: "var(--ink-3)" }}>
                    <Ico name="clock" size={13} /> {t("src.lastsync")} {ago(syncing[s.id] ? 0 : s.lastSync)}
                    {s.autoSync && (<span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: "var(--accent)" }}><Ico name="refresh" size={12} /> auto</span>)}
                  </span>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <Btn kind="default" size="sm" icon="refresh" onClick={() => syncNow(s.id)} disabled={syncing[s.id] || s.status === "disabled"}>
                      {syncing[s.id] ? t("src.syncing") : t("src.syncnow")}
                    </Btn>
                    <Kebab items={[{ label: "Edit", icon: "sliders", onClick: () => setEditing(s) }, { label: s.status === "disabled" ? "Enable" : "Disable", icon: "power", onClick: () => toggleEnabled(s) }, { label: "Delete", icon: "x", danger: true, onClick: () => setDeleting(s) }]} />
                  </div>
                </div>
                {s.status === "error" && s.lastError && (
                  <div style={{ marginTop: 12, padding: "9px 12px", borderRadius: 5, background: "var(--red-bg)", display: "flex", gap: 8, alignItems: "flex-start" }}>
                    <Ico name="alert" size={14} stroke="var(--red)" style={{ marginTop: 1, flexShrink: 0 }} />
                    <span className="mono" style={{ fontSize: 11, color: "var(--red)", lineHeight: 1.5 }}>{s.lastError}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
      {showReg && <RegisterModal t={t} clientOptions={clientsLive.data} onClose={() => setShowReg(false)} onSubmit={register} />}
      {editing && <EditModal t={t} src={editing} onClose={() => setEditing(null)} onSubmit={saveEdit} />}
      {deleting && (
        <Modal onClose={() => setDeleting(null)}>
          <h3 style={{ fontSize: 17, marginBottom: 10 }}>{t("src.delTitle")}</h3>
          <p style={{ fontSize: 13, color: "var(--ink-2)", lineHeight: 1.55, margin: "0 0 6px" }}>{t("src.delBody")}</p>
          <p className="mono" style={{ fontSize: 12, color: "var(--ink-3)", margin: 0 }}>{deleting.label}</p>
          <p style={{ fontSize: 12, color: "var(--ink-4)", lineHeight: 1.5, marginTop: 10 }}>{t("src.delNote")}</p>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--line-2)" }}>
            <Btn kind="default" onClick={() => setDeleting(null)}>{t("src.cancel")}</Btn>
            <Btn kind="danger" icon="x" onClick={confirmDelete}>{t("src.delConfirm")}</Btn>
          </div>
        </Modal>
      )}
    </div>
  );
}

function EditModal({ t, src, onClose, onSubmit }: { t: TFn; src: Source; onClose: () => void; onSubmit: (f: { label: string; cred: string; autoSync: boolean }) => void }) {
  const [label, setLabel] = useState(src.label);
  const [cred, setCred] = useState(src.cred || D.CREDENTIALS[0]);
  const [autoSync, setAutoSync] = useState(src.autoSync);
  return (
    <Modal onClose={onClose} wide>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <h3 style={{ fontSize: 17 }}>{t("src.editTitle")}</h3>
        <button onClick={onClose} style={{ border: "none", background: "transparent", color: "var(--ink-3)" }}><Ico name="x" size={18} /></button>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 15 }}>
        <Field label={t("src.uri")}>
          <input value={src.uri} disabled style={{ ...fieldInput, fontFamily: '"IBM Plex Mono", monospace', color: "var(--ink-3)", background: "var(--panel-3)" }} />
        </Field>
        <Field label={t("src.label")}>
          <input value={label} onChange={(e) => setLabel(e.target.value)} style={fieldInput} />
        </Field>
        <Field label={t("src.cred")}>
          <Select value={cred} onChange={setCred} options={D.CREDENTIALS.map((c) => ({ v: c, l: c }))} full />
        </Field>
        <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", padding: "2px 0" }}>
          <Toggle on={autoSync} onChange={() => setAutoSync((v) => !v)} />
          <span style={{ fontSize: 13 }}>{t("src.autosync")}</span>
        </label>
      </div>
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--line-2)" }}>
        <Btn kind="default" onClick={onClose}>{t("src.cancel")}</Btn>
        <Btn kind="primary" icon="check" disabled={label.trim().length < 2} onClick={() => onSubmit({ label, cred, autoSync })}>{t("src.save")}</Btn>
      </div>
    </Modal>
  );
}

function RegisterModal({ t, clientOptions, onClose, onSubmit }: { t: TFn; clientOptions: SelectOption[]; onClose: () => void; onSubmit: (f: { type: "s3" | "url"; uri: string; label: string; client: string; cred: string; autoSync: boolean }) => void }) {
  const [type, setType] = useState<"s3" | "url">("s3");
  const [uri, setUri] = useState("");
  const [label, setLabel] = useState("");
  const [client, setClient] = useState(clientOptions[0]?.v || "");
  const [cred, setCred] = useState(D.CREDENTIALS[0]);
  const [autoSync, setAutoSync] = useState(true);
  const [showSampling, setShowSampling] = useState(false);

  const uriValid = type === "s3" ? /^s3:\/\/[\w.-]+\/.*/.test(uri) : /^https?:\/\/.+/.test(uri);
  const placeholder = type === "s3" ? "s3://bucket/prefix/" : "https://…/listing.json";
  const canSubmit = uriValid && label.trim().length > 1;

  return (
    <Modal onClose={onClose} wide>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <h3 style={{ fontSize: 17 }}>{t("src.register")}</h3>
        <button onClick={onClose} style={{ border: "none", background: "transparent", color: "var(--ink-3)" }}><Ico name="x" size={18} /></button>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 15 }}>
        <Field label={t("src.type")}>
          <Segment value={type} onChange={(v) => setType(v as "s3" | "url")} size="md" options={[{ value: "s3", label: "S3", icon: "database" }, { value: "url", label: "URL", icon: "link" }]} />
        </Field>
        <Field label={t("src.uri")} hint={uri && !uriValid ? `Expected ${type === "s3" ? "s3://bucket/prefix/" : "https://…"}` : null}>
          <span style={{ position: "relative", display: "block" }}>
            <input value={uri} onChange={(e) => setUri(e.target.value)} placeholder={placeholder} style={{ ...fieldInput, fontFamily: '"IBM Plex Mono", monospace', paddingRight: 34, borderColor: uri ? (uriValid ? "var(--green)" : "var(--amber)") : "var(--line-strong)" }} />
            {uri && <span style={{ position: "absolute", right: 11, top: "50%", transform: "translateY(-50%)" }}><Ico name={uriValid ? "check" : "alert"} size={15} stroke={uriValid ? "var(--green)" : "var(--amber)"} /></span>}
          </span>
        </Field>
        <Field label={t("src.label")}>
          <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Halo — daily shift uploads" style={fieldInput} />
        </Field>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <Field label={t("src.client")}>
            <Select value={client} onChange={setClient} options={clientOptions} full />
          </Field>
          <Field label={t("src.cred")}>
            <Select value={cred} onChange={setCred} options={D.CREDENTIALS.map((c) => ({ v: c, l: c }))} full />
          </Field>
        </div>
        <button onClick={() => setShowSampling((s) => !s)} style={{ display: "flex", alignItems: "center", gap: 7, border: "none", background: "transparent", color: "var(--ink-2)", fontSize: 12.5, padding: 0, width: "fit-content" }}>
          <Ico name="chevR" size={13} style={{ transform: showSampling ? "rotate(90deg)" : "none", transition: "transform .15s" }} />
          {t("src.sampling")} <span style={{ color: "var(--ink-4)" }}>(optional)</span>
        </button>
        {showSampling && (
          <div className="fade-in" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, padding: "2px 0 2px 20px" }}>
            <Field label="Frame interval (s)"><input type="number" defaultValue="2" style={fieldInput} /></Field>
            <Field label="Max frames"><input type="number" defaultValue="40" style={fieldInput} /></Field>
          </div>
        )}
        <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", padding: "2px 0" }}>
          <Toggle on={autoSync} onChange={() => setAutoSync((v) => !v)} />
          <span style={{ fontSize: 13 }}>{t("src.autosync")}</span>
        </label>
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--line-2)" }}>
        <button style={{ border: "none", background: "transparent", color: "var(--accent)", fontSize: 12.5, fontWeight: 550, display: "flex", alignItems: "center", gap: 5 }}>
          <Ico name="shield" size={13} /> {t("src.manageCred")}
        </button>
        <div style={{ display: "flex", gap: 8 }}>
          <Btn kind="default" onClick={onClose}>{t("src.cancel")}</Btn>
          <Btn kind="primary" icon="refresh" disabled={!canSubmit} onClick={() => onSubmit({ type, uri, label, client, cred, autoSync })}>{t("src.regscan")}</Btn>
        </div>
      </div>
    </Modal>
  );
}

function SourceDetail({ t, src, onBack, onSync, onOpenReview }: { t: TFn; src: Source; onBack: () => void; onSync: () => void; onOpenReview: (id: string) => void }) {
  const vidsLive = useLive<BoardVideo[]>(() => api.boardVideos(src.id), [], [src.id]);
  const vids = vidsLive.data;
  const stats: [string, number, string][] = [
    ["total", src.total, "var(--ink)"],
    ["ingested", src.ingested, "var(--accent)"],
    ["in review", src.inReview, "var(--amber)"],
    ["done", src.done, "var(--green)"],
    ["failed", src.failed, "var(--red)"],
    ["to ingest", src.toGo, "var(--ink-2)"],
  ];
  return (
    <div style={{ height: "100%", overflow: "auto", background: "var(--bg)" }}>
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "24px 28px 60px" }}>
        <Btn kind="ghost" size="sm" icon="arrowL" onClick={onBack} style={{ marginBottom: 14, marginLeft: -6 }}>{t("src.title")}</Btn>
        <div className="panel" style={{ padding: 18, marginBottom: 18 }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 14 }}>
            <span style={{ width: 44, height: 44, borderRadius: 8, flexShrink: 0, display: "grid", placeItems: "center", background: "var(--panel-3)", border: "1px solid var(--line)", color: "var(--ink-2)" }}>
              <Ico name={src.type === "s3" ? "database" : "link"} size={21} />
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <h1 style={{ fontSize: 20, letterSpacing: "-0.01em" }}>{src.label}</h1>
              <div className="mono" style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>{src.uri}</div>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 9 }}>
                <ClientChip client={src.clientObj} />
                <StatusBadge status={src.status} label={t("src." + src.status)} />
              </div>
            </div>
            <Btn kind="default" icon="refresh" onClick={onSync} disabled={src.status === "disabled"}>{t("src.syncnow")}</Btn>
          </div>
          {src.total > 0 && (
            <div style={{ marginTop: 18 }}>
              <FunnelBar src={src} height={11} />
              <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 1, marginTop: 12, background: "var(--line)", border: "1px solid var(--line)", borderRadius: 6, overflow: "hidden" }}>
                {stats.map(([l, v, c]) => (
                  <div key={l} style={{ background: "var(--panel)", padding: "11px 12px" }}>
                    <div className="mono tnum" style={{ fontSize: 22, fontWeight: 600, color: c }}>{v}</div>
                    <div className="label" style={{ marginTop: 3 }}>{l}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {src.status === "error" && src.lastError && (
          <div className="panel" style={{ padding: 16, marginBottom: 18, borderColor: "var(--red)" }}>
            <div className="label" style={{ color: "var(--red)", marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}>
              <Ico name="alert" size={13} /> {t("src.errpanel")}
            </div>
            <p className="mono" style={{ margin: 0, fontSize: 12, color: "var(--red)", lineHeight: 1.55 }}>{src.lastError}</p>
            <Btn kind="default" size="sm" icon="refresh" onClick={onSync} style={{ marginTop: 12 }}>{t("common.retry")}</Btn>
          </div>
        )}

        <div className="label" style={{ marginBottom: 10 }}>{t("src.videos")} <span className="mono tnum" style={{ color: "var(--ink-3)", fontWeight: 400 }}>{vids.length}</span></div>
        {vids.length === 0 ? (
          <EmptyState icon="film" title="No videos discovered yet" sub="Run a sync to enumerate this source." />
        ) : (
          <div className="panel" style={{ overflow: "hidden" }}>
            <Row head cols="48px 1.1fr 90px 130px 70px 70px">
              {["", t("queue.ref"), t("queue.scene"), t("portal.status"), "AI", ""].map((h, i) => (
                <span key={i} className="label" style={{ textAlign: i === 4 ? "right" : "left" }}>{h}</span>
              ))}
            </Row>
            {vids.map((v, i) => (
              <Row key={v.id} cols="48px 1.1fr 90px 130px 70px 70px" last={i === vids.length - 1} onClick={() => onOpenReview(v.id)}>
                <FrameThumb frame={{ hue: sceneOf(v.scene).hue }} style={{ width: 40, height: 24 }} showHud={false} />
                <span className="mono" style={{ fontWeight: 600, fontSize: 12.5 }}>{v.ref}</span>
                <span className="mono" style={{ fontSize: 11, color: "var(--ink-2)" }}>{sceneOf(v.scene).label}</span>
                <StatusBadge status={VIDEO_PILL[v.status] || "processing"} size="sm" />
                <span style={{ textAlign: "right" }}><Grade value={v.aiGrade} size={12.5} /></span>
                <span style={{ textAlign: "right", color: "var(--ink-4)" }}><Ico name="chevR" size={15} /></span>
              </Row>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
