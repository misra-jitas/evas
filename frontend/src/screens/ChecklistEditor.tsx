// Shared review-config editor: checklist items (any type) + prompt framing.
// Used by the Clients "Review config" action and the Checklists admin screen.
// Saving always creates a new immutable version and activates it.
import { useEffect, useState } from "react";
import { api, type ChecklistConfig, type ChecklistItem, type ItemType } from "../api";
import { Btn, Field, fieldInput, Ico, Modal, Select } from "../components";
import type { TFn } from "../types";

const TYPE_OPTIONS = [
  { v: "boolean", l: "Yes / no" },
  { v: "category", l: "Choose one" },
  { v: "multi_boolean", l: "Several yes/no" },
  { v: "text", l: "Free text" },
  { v: "number", l: "Number" },
];

const csv = (xs: string[]) => xs.join(", ");
const parseCsv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
const subKeys = (it: ChecklistItem) =>
  Array.isArray(it.options) ? (it.options as { key: string }[]).map((o) => o.key) : [];

function blankItem(): ChecklistItem {
  return { key: "", label: "", type: "boolean", weight: 1 };
}

export function ChecklistEditor({
  t,
  client,
  initial,
  onClose,
  onSaved,
}: {
  t: TFn;
  client: { id: string; name: string; slug: string };
  initial?: ChecklistConfig | null;
  onClose: () => void;
  onSaved?: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? `${client.slug}_v1`);
  const [grading, setGrading] = useState(initial?.grading_mode ?? "derived");
  const [prompt, setPrompt] = useState(initial?.prompt_template ?? "");
  const [items, setItems] = useState<ChecklistItem[]>(initial?.items?.length ? initial.items : [blankItem()]);
  // When no explicit `initial` was passed, fetch the client's active checklist as the starting point.
  const [loading, setLoading] = useState(initial === undefined);
  const [version, setVersion] = useState<number | null>(initial?.version ?? null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (initial !== undefined) return; // caller supplied the starting state (incl. null = brand new)
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
  }, [client.id, initial]);

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
      .then(() => {
        onSaved?.();
        onClose();
      })
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
