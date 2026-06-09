// App shell: auth + role routing, theme + i18n, top nav, and the reviewer
// ergonomics flow (instant submit→next, break nudge, end-of-session summary).
import { useEffect, useMemo, useState } from "react";
import { BOOTSTRAP_CONFIGURED, login as apiLogin, setToken } from "./api";
import { Btn, ClientChip, Ico, Modal, Segment, Stat } from "./components";
import { D } from "./data";
import { makeT } from "./i18n";
import { AIReviewScreen } from "./screens/AiReview";
import { ClientsScreen } from "./screens/Clients";
import { DashboardScreen } from "./screens/Dashboard";
import { PortalScreen } from "./screens/Portal";
import { QueueScreen, type SessionState } from "./screens/Queue";
import { ReviewScreen, type SubmitResult } from "./screens/Review";
import { SourcesScreen } from "./screens/Sources";
import type { Lang, Role, TFn, Theme } from "./types";

interface Route {
  screen: string;
  id?: string;
  qa?: boolean;
}

function Logo({ size = 22, color }: { size?: number; color?: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 9 }}>
      <span style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
          <rect x="1" y="1" width="22" height="22" rx="4" fill={color || "var(--accent)"} />
          <circle cx="12" cy="12" r="5.2" fill="none" stroke="var(--accent-ink)" strokeWidth="1.7" />
          <circle cx="12" cy="12" r="1.7" fill="var(--accent-ink)" />
        </svg>
      </span>
      <span style={{ fontWeight: 700, fontSize: size * 0.7, letterSpacing: "0.04em", fontFamily: '"IBM Plex Mono", monospace' }}>EVAS</span>
    </span>
  );
}

function ThemeToggle({ theme, setTheme }: { theme: Theme; setTheme: (t: Theme) => void }) {
  return (
    <button onClick={() => setTheme(theme === "dark" ? "light" : "dark")} title="Theme" style={{ width: 30, height: 30, borderRadius: 5, border: "1px solid var(--line)", background: "var(--panel)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--ink-2)" }}>
      <Ico name={theme === "dark" ? "sun" : "moon"} size={16} />
    </button>
  );
}

function UserMenu({ t, lang, setLang, role, onSignOut, current }: { t: TFn; lang: Lang; setLang: (l: Lang) => void; role: string; onSignOut: () => void; current: { name: string; initials: string; id: string } }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const h = () => setOpen(false);
    window.addEventListener("click", h);
    return () => window.removeEventListener("click", h);
  }, [open]);
  return (
    <div style={{ position: "relative" }} onClick={(e) => e.stopPropagation()}>
      <button onClick={() => setOpen((o) => !o)} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 8px 4px 4px", borderRadius: 6, border: "1px solid var(--line)", background: "var(--panel)" }}>
        <span style={{ width: 24, height: 24, borderRadius: 99, background: "var(--accent)", color: "var(--accent-ink)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 700 }}>{current.initials}</span>
        <span style={{ fontSize: 12.5, fontWeight: 500 }}>{current.name.split(" ")[0]}</span>
        <Ico name="chevD" size={13} stroke="var(--ink-3)" />
      </button>
      {open && (
        <div className="panel" style={{ position: "absolute", right: 0, top: 38, width: 230, padding: 6, zIndex: 70, boxShadow: "var(--shadow-pop)", animation: "evas-pop .14s both" }}>
          <div style={{ padding: "8px 10px 10px", borderBottom: "1px solid var(--line-2)", marginBottom: 6 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{current.name}</div>
            <div className="mono" style={{ fontSize: 10.5, color: "var(--ink-3)", marginTop: 2 }}>{role} · {current.id}</div>
          </div>
          <div style={{ padding: "6px 10px" }}>
            <div className="label" style={{ marginBottom: 6 }}>{t("common.lang")}</div>
            <Segment value={lang} onChange={(v) => setLang(v as Lang)} options={[{ value: "en", label: "EN" }, { value: "es", label: "ES" }]} />
          </div>
          <button onClick={onSignOut} style={{ display: "flex", alignItems: "center", gap: 8, width: "100%", padding: "8px 10px", border: "none", background: "transparent", color: "var(--ink-2)", fontSize: 13, borderRadius: 4, marginTop: 4 }} onMouseEnter={(e) => (e.currentTarget.style.background = "var(--panel-2)")} onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
            <Ico name="logout" size={15} /> {t("common.signout")}
          </button>
        </div>
      )}
    </div>
  );
}

function TopBar({ t, role, route, setRoute, theme, setTheme, lang, setLang, onSignOut, current, portalClient }: { t: TFn; role: Role; route: Route; setRoute: (r: Route) => void; theme: Theme; setTheme: (t: Theme) => void; lang: Lang; setLang: (l: Lang) => void; onSignOut: () => void; current: { name: string; initials: string; id: string }; portalClient: typeof D.CLIENTS[number] }) {
  const navs: Record<Role, { k: string; icon: string; l: string }[]> = {
    reviewer: [{ k: "queue", icon: "list", l: t("nav.queue") }],
    admin: [
      { k: "sources", icon: "database", l: t("nav.sources") },
      { k: "clients", icon: "user", l: t("nav.clients") },
      { k: "dashboard", icon: "grid", l: t("nav.dashboard") },
      { k: "videos", icon: "film", l: t("nav.videos") },
      { k: "aireview", icon: "cpu", l: t("nav.aireview") },
      { k: "jobs", icon: "layers", l: t("nav.jobs") },
    ],
    client: [
      { k: "portal", icon: "film", l: t("nav.portal") },
      { k: "exports", icon: "download", l: t("nav.exports") },
    ],
  };
  const activeKey = ({ detail: "sources", run: "aireview", review: role === "admin" ? "videos" : "queue" } as Record<string, string>)[route.screen] || route.screen;
  return (
    <header style={{ display: "flex", alignItems: "center", gap: 18, padding: "0 18px", height: 52, borderBottom: "1px solid var(--line)", background: "var(--panel)", flexShrink: 0, zIndex: 40 }}>
      <Logo />
      <div style={{ width: 1, height: 22, background: "var(--line)" }} />
      {role === "client" ? <ClientChip client={portalClient} /> : <span className="label" style={{ fontSize: 10 }}>{role === "reviewer" ? t("role.reviewer") : t("role.admin")}</span>}
      <nav style={{ display: "flex", gap: 2, marginLeft: 6 }}>
        {navs[role].map((n) => {
          const active = activeKey === n.k;
          return (
            <button key={n.k} onClick={() => setRoute({ screen: n.k })} style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 11px", borderRadius: 6, border: "none", fontSize: 13, fontWeight: 500, background: active ? "var(--accent-2)" : "transparent", color: active ? "var(--accent)" : "var(--ink-2)", transition: "background .12s" }}>
              <Ico name={n.icon} size={15} /> {n.l}
            </button>
          );
        })}
      </nav>
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
        {role === "reviewer" && (
          <button onClick={() => setRoute({ qa: true, screen: "review", id: "EGO-24799" })} title="QA review mode" style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 9px", borderRadius: 6, border: "1px solid var(--line)", background: "var(--panel)", fontSize: 12, color: "var(--ink-2)" }}>
            <Ico name="shield" size={14} stroke="var(--violet)" /> QA mode
          </button>
        )}
        <ThemeToggle theme={theme} setTheme={setTheme} />
        <UserMenu t={t} lang={lang} setLang={setLang} role={role} onSignOut={onSignOut} current={current} />
      </div>
    </header>
  );
}

const inputStyle: React.CSSProperties = { padding: "9px 11px", borderRadius: 5, border: "1px solid var(--line-strong)", background: "var(--panel-2)", fontSize: 13, outline: "none" };

// Seeded demo accounts (see `evas create-user`). Each role logs in as the
// matching user so its JWT carries the right role for the live API.
const DEMO_EMAIL: Record<Role, string> = {
  reviewer: "elena.park@evas.io",
  admin: "admin@evas.io",
  client: "viewer@halo.io",
};

function Login({ t, onLogin, theme, setTheme }: { t: TFn; onLogin: (role: Role, email: string) => void; theme: Theme; setTheme: (t: Theme) => void }) {
  const roles: { k: Role; icon: string; title: string; desc: string }[] = [
    { k: "reviewer", icon: "list", title: t("role.reviewer"), desc: "Clear assigned videos, keyboard-first." },
    { k: "admin", icon: "grid", title: t("role.admin"), desc: "Pipeline, discrepancies, throughput, cost." },
    { k: "client", icon: "film", title: t("role.client"), desc: "Read-only results for your videos." },
  ];
  const [hover, setHover] = useState<Role>("reviewer");
  const [email, setEmail] = useState(DEMO_EMAIL.reviewer);
  const [edited, setEdited] = useState(false);
  // Until the user edits the field, it tracks the hovered role's demo account.
  function hoverRole(r: Role) {
    setHover(r);
    if (!edited) setEmail(DEMO_EMAIL[r]);
  }
  return (
    <div className="grid-tex" style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", position: "relative" }}>
      <div style={{ position: "absolute", top: 16, right: 16 }}><ThemeToggle theme={theme} setTheme={setTheme} /></div>
      <div className="fade-in" style={{ width: 440, maxWidth: "92%" }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginBottom: 24 }}>
          <Logo size={34} />
          <p style={{ color: "var(--ink-3)", fontSize: 13, marginTop: 12 }}>{t("login.sub")}</p>
        </div>
        <div className="panel" style={{ padding: 22, boxShadow: "var(--shadow-2)" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 11, marginBottom: 18 }}>
            <label style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <span className="label">{t("login.email")}</span>
              <input value={email} onChange={(e) => { setEmail(e.target.value); setEdited(true); }} style={inputStyle} />
            </label>
            <label style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <span className="label">{t("login.pass")}</span>
              <input type="password" defaultValue="evas-demo" style={inputStyle} />
            </label>
          </div>
          <div className="label" style={{ marginBottom: 9 }}>{t("login.as")}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            {roles.map((r) => (
              <button key={r.k} onClick={() => onLogin(r.k, edited ? email : DEMO_EMAIL[r.k])} onMouseEnter={() => hoverRole(r.k)} style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 13px", borderRadius: 6, border: `1px solid ${hover === r.k ? "var(--accent)" : "var(--line-strong)"}`, textAlign: "left", background: hover === r.k ? "var(--accent-2)" : "var(--panel)", transition: "all .12s" }}>
                <span style={{ width: 32, height: 32, borderRadius: 6, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", background: hover === r.k ? "var(--accent)" : "var(--panel-3)", color: hover === r.k ? "var(--accent-ink)" : "var(--ink-2)" }}>
                  <Ico name={r.icon} size={17} />
                </span>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ display: "block", fontSize: 13.5, fontWeight: 600 }}>{r.title}</span>
                  <span style={{ display: "block", fontSize: 11.5, color: "var(--ink-3)" }}>{r.desc}</span>
                </span>
                <Ico name="arrowR" size={16} stroke={hover === r.k ? "var(--accent)" : "var(--ink-4)"} />
              </button>
            ))}
          </div>
        </div>
        <p style={{ textAlign: "center", fontSize: 11, color: "var(--ink-4)", marginTop: 14 }}>Role-based routing · JWT · audit hooks on every write</p>
      </div>
    </div>
  );
}

function SessionSummary({ t, s, onClose }: { t: TFn; s: { count: number; agreement: number }; onClose: () => void }) {
  return (
    <Modal onClose={onClose}>
      <div style={{ textAlign: "center" }}>
        <div style={{ width: 56, height: 56, borderRadius: 99, background: "var(--green-bg)", margin: "0 auto 16px", display: "grid", placeItems: "center" }}>
          <Ico name="award" size={30} stroke="var(--green)" sw={2} />
        </div>
        <h3 style={{ fontSize: 19, marginBottom: 6 }}>{t("erg.niceRun")}</h3>
        <p style={{ color: "var(--ink-2)", fontSize: 13, marginBottom: 20 }}>{t("erg.allclearsub")}</p>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1, background: "var(--line)", border: "1px solid var(--line)", borderRadius: 8, overflow: "hidden", marginBottom: 20 }}>
          <Stat label={t("erg.summary")} value={s.count} />
          <Stat label={t("erg.agreement")} value={s.agreement + "%"} tone="var(--green)" />
        </div>
        <Btn kind="primary" size="lg" onClick={onClose} style={{ width: "100%", justifyContent: "center" }}>{t("erg.backqueue")}</Btn>
      </div>
    </Modal>
  );
}

export function App() {
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem("evas-theme") as Theme | null;
    if (saved) return saved;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });
  const [lang, setLang] = useState<Lang>(() => (localStorage.getItem("evas-lang") as Lang) || "en");
  const [soundOn, setSoundOn] = useState(() => localStorage.getItem("evas-sound") === "1");
  const [role, setRole] = useState<Role | null>(null);
  const [route, setRoute] = useState<Route>({ screen: "queue" });
  const [summary, setSummary] = useState<{ count: number; agreement: number } | null>(null);
  const [breakNudge, setBreakNudge] = useState(false);
  const [session, setSession] = useState<SessionState>({ reviewedToday: 13, target: 50, streak: 0, agreeSum: 0, agreeCount: 0 });

  const t = useMemo(() => makeT(lang), [lang]);
  const portalClient = D.CLIENTS[0];

  const order: Record<string, number> = { rush: 0, high: 1, normal: 2 };
  const sortedQueue = useMemo(() => [...D.QUEUE].sort((a, b) => order[a.priority] - order[b.priority] || b.assignedMins - a.assignedMins), []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("evas-theme", theme);
  }, [theme]);
  useEffect(() => {
    localStorage.setItem("evas-lang", lang);
  }, [lang]);
  function toggleSound() {
    setSoundOn((s) => {
      localStorage.setItem("evas-sound", s ? "0" : "1");
      return !s;
    });
  }

  async function login(r: Role, email: string) {
    // Mint the JWT BEFORE routing so the first screen's fetch is authenticated
    // (otherwise it races the token and 401s into the mock fallback). Best-effort:
    // only when a bootstrap token is configured; failures fall back to mock.
    if (BOOTSTRAP_CONFIGURED && email) {
      try {
        await apiLogin(email);
      } catch {
        /* offline / unknown user — proceed with mock data */
      }
    }
    setRole(r);
    setRoute({ screen: r === "reviewer" ? "queue" : r === "admin" ? "sources" : "portal" });
  }
  function signOut() {
    setToken(null);
    setRole(null);
    setSummary(null);
    setBreakNudge(false);
  }

  function onReviewSubmitted(r: SubmitResult) {
    setSession((s) => {
      const streak = s.streak + 1;
      const agreeCount = s.agreeCount + (r.agreement != null ? 1 : 0);
      const agreeSum = s.agreeSum + (r.agreement != null ? r.agreement : 96);
      if (streak > 0 && streak % 6 === 0) setBreakNudge(true);
      return { ...s, reviewedToday: s.reviewedToday + 1, streak, agreeSum, agreeCount };
    });
    // Mock reviews chain to the next mock item; live reviews (ref not in the
    // mock queue) return to the Queue, which reloads from the board with the
    // just-reviewed video now dropped out (it's human_reviewed).
    const idx = sortedQueue.findIndex((q) => q.id === r.ref);
    const next = idx >= 0 ? sortedQueue[idx + 1] : undefined;
    if (next) setRoute({ screen: "review", id: next.id });
    else {
      setRoute({ screen: "queue" });
      setSummary({ count: session.reviewedToday + 1, agreement: Math.round((session.agreeSum + 96) / (session.agreeCount + 1)) });
    }
  }

  if (!role) return <Login t={t} onLogin={login} theme={theme} setTheme={setTheme} />;

  const current =
    role === "reviewer"
      ? D.CURRENT
      : role === "admin"
        ? { id: "admin", name: "Ops Admin", initials: "OA", role: "admin" }
        : { id: "client", name: "Halo Viewer", initials: "HV", role: "client_viewer" };

  let body: React.ReactNode;
  if (role === "reviewer") {
    if (route.screen === "review") {
      body = (
        <ReviewScreen
          key={(route.id || "") + (route.qa ? "-qa" : "")}
          t={t}
          reviewId={route.id || sortedQueue[0].id}
          qaMode={!!route.qa}
          session={session}
          soundOn={soundOn}
          onToggleSound={toggleSound}
          onExit={() => setRoute({ screen: "queue" })}
          onSubmitted={route.qa ? () => setRoute({ screen: "queue" }) : onReviewSubmitted}
        />
      );
    } else {
      body = <QueueScreen t={t} session={session} onOpen={(id) => setRoute({ screen: "review", id })} />;
    }
  } else if (role === "admin") {
    if (route.screen === "review") {
      body = <ReviewScreen key={route.id} t={t} reviewId={route.id || sortedQueue[0].id} qaMode={false} soundOn={soundOn} onToggleSound={toggleSound} onExit={() => setRoute({ screen: "videos" })} onSubmitted={() => setRoute({ screen: "videos" })} />;
    } else if (route.screen === "sources" || route.screen === "detail") {
      body = <SourcesScreen t={t} sub={route.screen === "detail" ? "detail" : "list"} sourceId={route.id} onOpen={(screen, id) => setRoute({ screen: screen === "sources" ? "sources" : "detail", id })} onOpenReview={(id) => setRoute({ screen: "review", id })} />;
    } else if (route.screen === "aireview" || route.screen === "run") {
      body = <AIReviewScreen t={t} sub={route.screen === "run" ? "run" : "list"} runId={route.id} onOpen={(screen, id) => setRoute({ screen: screen === "aireview" ? "aireview" : "run", id })} onOpenDiscrepancy={() => setRoute({ screen: "dashboard" })} />;
    } else if (route.screen === "clients") {
      body = <ClientsScreen t={t} />;
    } else {
      body = <DashboardScreen t={t} sub={route.screen === "dashboard" ? null : route.screen} onOpenReview={(id) => setRoute({ screen: "review", id })} />;
    }
  } else {
    body = <PortalScreen t={t} sub={route.screen === "portal" ? null : route.screen} portalClient={portalClient} />;
  }

  const inReview = (role === "reviewer" || role === "admin") && route.screen === "review";
  const showChrome = !inReview;

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", background: "var(--bg)" }}>
      {showChrome && <TopBar t={t} role={role} route={route} setRoute={setRoute} theme={theme} setTheme={setTheme} lang={lang} setLang={setLang} onSignOut={signOut} current={current} portalClient={portalClient} />}
      <div style={{ flex: 1, minHeight: 0 }}>{body}</div>

      {summary && <SessionSummary t={t} s={summary} onClose={() => setSummary(null)} />}

      {breakNudge && inReview && (
        <div className="fade-in" style={{ position: "fixed", top: 64, right: 18, zIndex: 75, maxWidth: 290, display: "flex", gap: 12, padding: "13px 14px", borderRadius: 8, background: "var(--panel)", border: "1px solid var(--line-strong)", boxShadow: "var(--shadow-pop)" }}>
          <span style={{ width: 32, height: 32, borderRadius: 7, flexShrink: 0, display: "grid", placeItems: "center", background: "var(--amber-bg)", color: "var(--amber)" }}><Ico name="coffee" size={17} /></span>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 12.5, color: "var(--ink)", lineHeight: 1.5 }}>{t("erg.break").replace("{n}", String(session.streak))}</div>
            <button onClick={() => setBreakNudge(false)} style={{ marginTop: 7, border: "none", background: "transparent", color: "var(--ink-3)", fontSize: 12, fontWeight: 600, padding: 0 }}>{t("erg.dismiss")}</button>
          </div>
          <button onClick={() => setBreakNudge(false)} style={{ border: "none", background: "transparent", color: "var(--ink-4)", alignSelf: "flex-start" }}><Ico name="x" size={15} /></button>
        </div>
      )}
    </div>
  );
}
