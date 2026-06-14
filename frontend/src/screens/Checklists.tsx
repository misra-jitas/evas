// Checklist administrator (admin): create and maintain per-client checklists +
// prompts across clients. Wired to /clients and /clients/{id}/checklists.
// Editing or creating saves a new immutable version via the shared editor.
import { useEffect, useState } from "react";
import { api, type ChecklistConfig, type ChecklistItem, type ClientRecord, useLive } from "../api";
import { Btn, EmptyInline, Ico, Row, Select } from "../components";
import type { TFn } from "../types";
import { ChecklistEditor } from "./ChecklistEditor";

const COLS = "1.3fr 70px 1.4fr 90px 70px 64px";

function typeSummary(items: ChecklistItem[]): string {
  const counts: Record<string, number> = {};
  for (const it of items) counts[it.type || "boolean"] = (counts[it.type || "boolean"] || 0) + 1;
  const short: Record<string, string> = { boolean: "bool", category: "cat", multi_boolean: "multi", text: "text", number: "num" };
  return Object.entries(counts).map(([k, n]) => `${n} ${short[k] || k}`).join(" · ");
}

export function ChecklistsScreen({ t }: { t: TFn }) {
  const clients = useLive<ClientRecord[]>(() => api.listClients(), []);
  const [clientId, setClientId] = useState<string>("");
  const [lists, setLists] = useState<ChecklistConfig[]>([]);
  const [loading, setLoading] = useState(false);
  // null = brand-new checklist, a config = edit/clone that one, undefined = closed
  const [editing, setEditing] = useState<ChecklistConfig | null | undefined>(undefined);

  // Default to the first client once they load.
  useEffect(() => {
    if (!clientId && clients.data.length) setClientId(clients.data[0].id);
  }, [clients.data, clientId]);

  function reload(cid = clientId) {
    if (!cid) return;
    setLoading(true);
    api
      .listChecklists(cid)
      .then(setLists)
      .catch(() => setLists([]))
      .finally(() => setLoading(false));
  }
  useEffect(() => {
    reload(clientId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

  const client = clients.data.find((c) => c.id === clientId) || null;
  const clientOpts = clients.data.map((c) => ({ v: c.id, l: c.name }));

  return (
    <div style={{ height: "100%", overflow: "auto", background: "var(--bg)" }}>
      <div style={{ maxWidth: 1080, margin: "0 auto", padding: "26px 28px 60px" }}>
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16, marginBottom: 20, flexWrap: "wrap" }}>
          <div>
            <div className="label" style={{ marginBottom: 6 }}>{t("role.admin")}</div>
            <h1 style={{ fontSize: 26, letterSpacing: "-0.02em" }}>{t("nav.checklists")}</h1>
            <p style={{ color: "var(--ink-3)", fontSize: 13, marginTop: 4 }}>{t("checklists.sub")}</p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Select value={clientId} onChange={setClientId} options={clientOpts} icon="user" />
            <Btn kind="primary" size="lg" icon="plus" disabled={!clientId} onClick={() => setEditing(null)} style={{ boxShadow: "var(--shadow-2)" }}>
              {t("checklists.new")}
            </Btn>
          </div>
        </div>

        <div className="panel" style={{ overflow: "hidden", boxShadow: "var(--shadow-1)" }}>
          <Row head cols={COLS}>
            {[t("checklists.name"), t("checklists.version"), t("checklists.items"), t("checklists.grading"), t("checklists.prompt"), ""].map((h, i) => (
              <span key={i} className="label">{h}</span>
            ))}
          </Row>
          {loading ? (
            <div style={{ padding: 26, textAlign: "center", color: "var(--ink-3)", fontSize: 13 }}>Loading…</div>
          ) : lists.length === 0 ? (
            <EmptyInline icon="list" msg={t("checklists.empty")} />
          ) : (
            lists.map((cl, i) => (
              <Row key={cl.id} cols={COLS} last={i === lists.length - 1} onClick={() => setEditing(cl)}>
                <span style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                  <span className="mono" style={{ fontSize: 12.5, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{cl.name}</span>
                  {cl.is_active && (
                    <span style={{ fontSize: 10, fontWeight: 600, color: "var(--green)", background: "var(--green-bg)", padding: "1px 7px", borderRadius: 99, flexShrink: 0 }}>active</span>
                  )}
                </span>
                <span className="mono tnum" style={{ fontSize: 12.5 }}>v{cl.version}</span>
                <span style={{ fontSize: 12, color: "var(--ink-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {cl.items.length} · <span style={{ color: "var(--ink-3)" }}>{typeSummary(cl.items)}</span>
                </span>
                <span className="mono" style={{ fontSize: 11.5, color: "var(--ink-3)" }}>{cl.grading_mode}</span>
                <span style={{ fontSize: 11.5, color: cl.prompt_template ? "var(--accent)" : "var(--ink-4)" }}>
                  {cl.prompt_template ? "custom" : "default"}
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: 5, justifyContent: "flex-end", color: "var(--ink-3)", fontSize: 11 }}>
                  <Ico name="sliders" size={13} /> edit
                </span>
              </Row>
            ))
          )}
        </div>
        <p style={{ color: "var(--ink-4)", fontSize: 11.5, marginTop: 12 }}>{t("checklists.note")}</p>
      </div>

      {editing !== undefined && client && (
        <ChecklistEditor
          t={t}
          client={client}
          initial={editing}
          onClose={() => setEditing(undefined)}
          onSaved={() => reload()}
        />
      )}
    </div>
  );
}
