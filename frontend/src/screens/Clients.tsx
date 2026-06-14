// Client management (admin): add / rename / edit / delete clients.
// Wired to /clients CRUD with optimistic local updates + mock fallback.
import { useEffect, useState } from "react";
import { api, type ClientInput, type ClientRecord, useLive } from "../api";
import { Btn, EmptyInline, Field, fieldInput, Ico, Kebab, Modal, Row } from "../components";
import type { TFn } from "../types";
import { ChecklistEditor } from "./ChecklistEditor";

const COLS = "1.4fr 1fr 90px 110px 110px 44px";

export function ClientsScreen({ t }: { t: TFn }) {
  const live = useLive<ClientRecord[]>(() => api.listClients(), []);
  const [clients, setClients] = useState<ClientRecord[]>(live.data);
  const [editing, setEditing] = useState<ClientRecord | "new" | null>(null);
  const [configFor, setConfigFor] = useState<ClientRecord | null>(null);

  useEffect(() => setClients(live.data), [live.data]);

  function save(form: ClientInput, id?: string) {
    if (id) {
      setClients((prev) => prev.map((c) => (c.id === id ? { ...c, ...form } : c)));
      api.updateClient(id, form).then(() => live.reload()).catch(() => {});
    } else {
      const optimistic: ClientRecord = {
        id: "client-" + Date.now(),
        name: form.name,
        slug: form.slug,
        sampling_config: form.sampling_config || {},
        frame_retention_days: form.frame_retention_days ?? null,
        video_archive_days: form.video_archive_days ?? null,
        video_count: 0,
      };
      setClients((prev) => [optimistic, ...prev]);
      api.createClient(form).then(() => live.reload()).catch(() => {});
    }
    setEditing(null);
  }

  function remove(c: ClientRecord) {
    if (!window.confirm(`Delete client "${c.name}"? Its videos stay but the client is removed.`)) return;
    setClients((prev) => prev.filter((x) => x.id !== c.id));
    api.deleteClient(c.id).then(() => live.reload()).catch(() => {});
  }

  return (
    <div style={{ height: "100%", overflow: "auto", background: "var(--bg)" }}>
      <div style={{ maxWidth: 1080, margin: "0 auto", padding: "26px 28px 60px" }}>
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, marginBottom: 20, flexWrap: "wrap" }}>
          <div>
            <div className="label" style={{ marginBottom: 6 }}>{t("role.admin")}</div>
            <h1 style={{ fontSize: 26, letterSpacing: "-0.02em" }}>{t("nav.clients")}</h1>
            <p style={{ color: "var(--ink-3)", fontSize: 13, marginTop: 4 }}>{t("clients.sub")}</p>
          </div>
          <Btn kind="primary" size="lg" icon="plus" onClick={() => setEditing("new")} style={{ boxShadow: "var(--shadow-2)" }}>
            {t("clients.new")}
          </Btn>
        </div>

        <div className="panel" style={{ overflow: "hidden", boxShadow: "var(--shadow-1)" }}>
          <Row head cols={COLS}>
            {[t("clients.name"), t("clients.slug"), t("dash.videos"), t("clients.retention"), t("clients.archive"), ""].map((h, i) => (
              <span key={i} className="label">{h}</span>
            ))}
          </Row>
          {clients.length === 0 && <EmptyInline icon="user" msg={t("clients.empty")} />}
          {clients.map((c, i) => (
            <Row key={c.id} cols={COLS} last={i === clients.length - 1}>
              <span style={{ display: "flex", alignItems: "center", gap: 9 }}>
                <span style={{ width: 22, height: 22, borderRadius: 4, flexShrink: 0, display: "grid", placeItems: "center", background: "var(--accent-2)", color: "var(--accent)" }}>
                  <Ico name="user" size={13} />
                </span>
                <span style={{ fontSize: 13, fontWeight: 600 }}>{c.name}</span>
              </span>
              <span className="mono" style={{ fontSize: 12, color: "var(--ink-2)" }}>{c.slug}</span>
              <span className="mono tnum" style={{ fontSize: 13, fontWeight: 600 }}>{c.video_count}</span>
              <span className="mono tnum" style={{ fontSize: 12, color: "var(--ink-3)" }}>{c.frame_retention_days != null ? `${c.frame_retention_days}d` : "—"}</span>
              <span className="mono tnum" style={{ fontSize: 12, color: "var(--ink-3)" }}>{c.video_archive_days != null ? `${c.video_archive_days}d` : "—"}</span>
              <Kebab items={[{ label: t("clients.edit"), icon: "sliders", onClick: () => setEditing(c) }, { label: t("clients.reviewConfig"), icon: "list", onClick: () => setConfigFor(c) }, { label: t("clients.delete"), icon: "x", danger: true, onClick: () => remove(c) }]} />
            </Row>
          ))}
        </div>
      </div>
      {editing && <ClientModal t={t} initial={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSave={save} />}
      {configFor && <ChecklistEditor t={t} client={configFor} onClose={() => setConfigFor(null)} />}
    </div>
  );
}

function ClientModal({ t, initial, onClose, onSave }: { t: TFn; initial: ClientRecord | null; onClose: () => void; onSave: (f: ClientInput, id?: string) => void }) {
  const sc = (initial?.sampling_config || {}) as Record<string, number>;
  const [name, setName] = useState(initial?.name || "");
  const [slug, setSlug] = useState(initial?.slug || "");
  const [interval, setInterval] = useState(String(sc.interval_seconds ?? 5));
  const [maxFrames, setMaxFrames] = useState(String(sc.max_frames ?? 300));
  const [frameWidth, setFrameWidth] = useState(String(sc.frame_width ?? 1280));
  const [retention, setRetention] = useState(initial?.frame_retention_days != null ? String(initial.frame_retention_days) : "");
  const [archive, setArchive] = useState(initial?.video_archive_days != null ? String(initial.video_archive_days) : "");

  const slugValid = /^[a-z0-9][a-z0-9-]*$/.test(slug);
  const canSave = name.trim().length > 1 && slugValid;

  function submit() {
    const body: ClientInput = {
      name: name.trim(),
      slug: slug.trim(),
      sampling_config: { interval_seconds: +interval, max_frames: +maxFrames, frame_width: +frameWidth },
      frame_retention_days: retention === "" ? null : +retention,
      video_archive_days: archive === "" ? null : +archive,
    };
    onSave(body, initial?.id);
  }

  return (
    <Modal onClose={onClose} wide>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <h3 style={{ fontSize: 17 }}>{initial ? t("clients.edit") : t("clients.new")}</h3>
        <button onClick={onClose} style={{ border: "none", background: "transparent", color: "var(--ink-3)" }}><Ico name="x" size={18} /></button>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 15 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <Field label={t("clients.name")}>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Halo Robotics" style={fieldInput} />
          </Field>
          <Field label={t("clients.slug")} hint={slug && !slugValid ? "lowercase letters, digits, hyphens" : null}>
            <input value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="halo" disabled={!!initial} style={{ ...fieldInput, fontFamily: '"IBM Plex Mono", monospace', opacity: initial ? 0.6 : 1, borderColor: slug ? (slugValid ? "var(--green)" : "var(--amber)") : "var(--line-strong)" }} />
          </Field>
        </div>
        <div className="label">{t("clients.sampling")}</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
          <Field label="Interval (s)"><input type="number" value={interval} onChange={(e) => setInterval(e.target.value)} style={fieldInput} /></Field>
          <Field label="Max frames"><input type="number" value={maxFrames} onChange={(e) => setMaxFrames(e.target.value)} style={fieldInput} /></Field>
          <Field label="Frame width"><input type="number" value={frameWidth} onChange={(e) => setFrameWidth(e.target.value)} style={fieldInput} /></Field>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <Field label={`${t("clients.retention")} (${t("clients.daysOptional")})`}><input type="number" value={retention} onChange={(e) => setRetention(e.target.value)} placeholder="—" style={fieldInput} /></Field>
          <Field label={`${t("clients.archive")} (${t("clients.daysOptional")})`}><input type="number" value={archive} onChange={(e) => setArchive(e.target.value)} placeholder="—" style={fieldInput} /></Field>
        </div>
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--line-2)" }}>
        <Btn kind="default" onClick={onClose}>{t("src.cancel")}</Btn>
        <Btn kind="primary" icon="check" disabled={!canSave} onClick={submit}>{initial ? t("clients.save") : t("clients.create")}</Btn>
      </div>
    </Modal>
  );
}
