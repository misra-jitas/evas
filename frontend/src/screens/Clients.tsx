// Client management (admin): add / rename / edit / delete clients.
// Wired to /clients CRUD with optimistic local updates + mock fallback.
import { useEffect, useState } from "react";
import {
  api,
  type ChecklistItem,
  type ClientInput,
  type ClientRecord,
  type ItemType,
  useLive,
} from "../api";
import { Btn, EmptyInline, Field, fieldInput, Ico, Kebab, Modal, Row, Select } from "../components";
import type { TFn } from "../types";

const TYPE_OPTIONS = [
  { v: "boolean", l: "Yes / no" },
  { v: "category", l: "Choose one" },
  { v: "multi_boolean", l: "Several yes/no" },
  { v: "text", l: "Free text" },
  { v: "number", l: "Number" },
];

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

// ---- Review-config editor: checklist items (any type) + prompt framing ----
const csv = (xs: string[]) => xs.join(", ");
const parseCsv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
const subKeys = (it: ChecklistItem) =>
  Array.isArray(it.options) ? (it.options as { key: string }[]).map((o) => o.key) : [];

function blankItem(): ChecklistItem {
  return { key: "", label: "", type: "boolean", weight: 1 };
}

function ChecklistEditor({ t, client, onClose }: { t: TFn; client: ClientRecord; onClose: () => void }) {
  const [name, setName] = useState(`${client.slug}_v1`);
  const [grading, setGrading] = useState("derived");
  const [prompt, setPrompt] = useState("");
  const [items, setItems] = useState<ChecklistItem[]>([blankItem()]);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api
      .activeChecklist(client.id)
      .then((c) => {
        if (!live) return;
        setName(c.name);
        setGrading(c.grading_mode);
        setPrompt(c.prompt_template || "");
        setItems(c.items.length ? c.items : [blankItem()]);
        setVersion(c.version);
      })
      .catch(() => {}) // 404 → start fresh with defaults
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [client.id]);

  function patch(i: number, next: Partial<ChecklistItem>) {
    setItems((prev) => prev.map((it, j) => (j === i ? { ...it, ...next } : it)));
  }
  function setType(i: number, type: ItemType) {
    // Reset type-specific fields so we never carry a stale shape across types.
    patch(i, { type, options: undefined, compliant_values: undefined, compliant_range: undefined, min: undefined, max: undefined });
  }

  const valid =
    name.trim().length > 0 &&
    items.length > 0 &&
    items.every((it) => /^[a-z0-9_]+$/.test(it.key)) &&
    new Set(items.map((it) => it.key)).size === items.length;

  function save() {
    setSaving(true);
    setErr(null);
    api
      .saveChecklist(client.id, { name: name.trim(), items, prompt_template: prompt || null, grading_mode: grading })
      .then(() => onClose())
      .catch((e) => setErr(e?.message || "Save failed"))
      .finally(() => setSaving(false));
  }

  return (
    <Modal onClose={onClose} wide>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <div>
          <h3 style={{ fontSize: 17 }}>{t("clients.reviewConfig")} — {client.name}</h3>
          <p style={{ color: "var(--ink-3)", fontSize: 12, marginTop: 3 }}>
            {version != null ? `Editing creates version ${version + 1}` : "New checklist (version 1)"}. The output format is enforced automatically.
          </p>
        </div>
        <button onClick={onClose} style={{ border: "none", background: "transparent", color: "var(--ink-3)" }}><Ico name="x" size={18} /></button>
      </div>

      {loading ? (
        <div style={{ padding: 30, textAlign: "center", color: "var(--ink-3)" }}>Loading…</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 15, maxHeight: "62vh", overflow: "auto", paddingRight: 4 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr", gap: 12 }}>
            <Field label="Checklist name"><input value={name} onChange={(e) => setName(e.target.value)} style={{ ...fieldInput, fontFamily: '"IBM Plex Mono", monospace' }} /></Field>
            <Field label="Grading"><Select value={grading} onChange={setGrading} full options={[{ v: "derived", l: "Derived (weighted)" }, { v: "holistic", l: "Holistic (equal)" }]} /></Field>
          </div>

          <Field label="Prompt framing" hint="Who the model is and what it's judging. Leave blank for a generic auditor.">
            <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3} placeholder="You are a fish-identification auditor. You will be shown an image…" style={{ ...fieldInput, resize: "vertical", fontFamily: "inherit" }} />
          </Field>

          <div className="label" style={{ marginTop: 4 }}>Items</div>
          {items.map((it, i) => (
            <div key={i} className="panel" style={{ padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1.4fr 1fr 70px 32px", gap: 8, alignItems: "end" }}>
                <Field label="key" hint={it.key && !/^[a-z0-9_]+$/.test(it.key) ? "a–z, 0–9, _" : null}>
                  <input value={it.key} onChange={(e) => patch(i, { key: e.target.value })} placeholder="is_trout" style={{ ...fieldInput, fontFamily: '"IBM Plex Mono", monospace' }} />
                </Field>
                <Field label="label"><input value={it.label} onChange={(e) => patch(i, { label: e.target.value })} placeholder="The fish is a trout" style={fieldInput} /></Field>
                <Field label="type"><Select value={it.type} onChange={(v) => setType(i, v as ItemType)} full options={TYPE_OPTIONS} /></Field>
                <Field label="weight"><input type="number" value={it.weight ?? 1} onChange={(e) => patch(i, { weight: +e.target.value })} style={fieldInput} /></Field>
                <button title="Remove" onClick={() => setItems((prev) => prev.filter((_, j) => j !== i))} style={{ height: 34, border: "1px solid var(--line)", background: "var(--panel)", borderRadius: 5, color: "var(--red)" }}><Ico name="x" size={14} /></button>
              </div>

              {it.type === "category" && (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  <Field label="options (comma-separated)"><input value={csv((it.options as string[]) || [])} onChange={(e) => patch(i, { options: parseCsv(e.target.value) })} placeholder="trout, salmon, bass" style={fieldInput} /></Field>
                  <Field label="compliant values (graded as ✓)"><input value={csv(it.compliant_values || [])} onChange={(e) => patch(i, { compliant_values: parseCsv(e.target.value) })} placeholder="trout" style={fieldInput} /></Field>
                </div>
              )}
              {it.type === "multi_boolean" && (
                <Field label="sub-checks (comma-separated keys)"><input value={csv(subKeys(it))} onChange={(e) => patch(i, { options: parseCsv(e.target.value).map((k) => ({ key: k, label: k })) })} placeholder="has_spots, has_adipose_fin" style={fieldInput} /></Field>
              )}
              {it.type === "number" && (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1.4fr", gap: 8 }}>
                  <Field label="min"><input type="number" value={it.min ?? ""} onChange={(e) => patch(i, { min: e.target.value === "" ? undefined : +e.target.value })} style={fieldInput} /></Field>
                  <Field label="max"><input type="number" value={it.max ?? ""} onChange={(e) => patch(i, { max: e.target.value === "" ? undefined : +e.target.value })} style={fieldInput} /></Field>
                  <Field label="compliant range (lo, hi — optional)"><input value={it.compliant_range ? csv(it.compliant_range.map(String)) : ""} onChange={(e) => { const n = parseCsv(e.target.value).map(Number); patch(i, { compliant_range: n.length === 2 && n.every((x) => !isNaN(x)) ? [n[0], n[1]] : undefined }); }} placeholder="20, 60" style={fieldInput} /></Field>
                </div>
              )}
              {it.type === "text" && <p style={{ fontSize: 11.5, color: "var(--ink-4)" }}>Free-text answer — informational, not part of the grade.</p>}
            </div>
          ))}
          <Btn kind="default" icon="plus" onClick={() => setItems((prev) => [...prev, blankItem()])}>Add item</Btn>
          {err && <p style={{ color: "var(--red)", fontSize: 12.5 }}>{err}</p>}
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 18, paddingTop: 14, borderTop: "1px solid var(--line-2)" }}>
        <Btn kind="default" onClick={onClose}>{t("src.cancel")}</Btn>
        <Btn kind="primary" icon="check" disabled={!valid || saving} onClick={save}>{saving ? "Saving…" : "Save new version"}</Btn>
      </div>
    </Modal>
  );
}
