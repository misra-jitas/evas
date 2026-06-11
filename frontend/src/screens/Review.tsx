// Reviewer Workbench: Review screen — the keyboard-first "money screen".
// Split layout, three-state checklist, derived grade, undo, autosave, instant
// submit→next, fading shortcut hints. Operates on the rich mock review model
// (frame-level findings); live human-review writes are a documented follow-up.
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { api, buildFrameOverrides } from "../api";
import { Btn, ClientChip, ConfBar, FrameThumb, Grade, Ico, Meta, Modal, Stat } from "../components";
import { D, sceneOf } from "../data";
import type { Frame, ItemState, Review, TFn } from "../types";
import type { SessionState } from "./Queue";

export interface SubmitResult {
  ref: string;
  grade: number;
  overrides: number;
  reviewed: number;
  total: number;
  agreement: number | null;
}

let audioCtx: AudioContext | null = null;

interface ReviewScreenProps {
  t: TFn;
  reviewId: string;
  qaMode: boolean;
  onExit: () => void;
  onSubmitted: (r: SubmitResult) => void;
  session?: SessionState;
  soundOn: boolean;
  onToggleSound: () => void;
}

// Resolves the review model: live (a real video UUID → GET /videos/{id} + media)
// or the bundled mock. Shows a loader until the live model arrives, then renders
// the workbench. Submitting a live review writes through the human-review API.
export function ReviewScreen(props: ReviewScreenProps) {
  const { t, reviewId, onExit } = props;
  const isLive = /^[0-9a-f-]{36}$/i.test(reviewId);
  const [model, setModel] = useState<Review | null>(isLive ? null : D.getReview(reviewId));
  const [mediaUrl, setMediaUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!isLive) {
      setModel(D.getReview(reviewId));
      setMediaUrl(null);
      return;
    }
    let alive = true;
    setModel(null);
    setFailed(false);
    Promise.all([api.videoReview(reviewId), api.videoMedia(reviewId).catch(() => null)])
      .then(([m, media]) => {
        if (!alive) return;
        setModel(m);
        setMediaUrl(media?.url ?? null);
      })
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [reviewId, isLive]);

  const persist = useCallback(
    (payload: { grade: number; notes: string; frames: Frame[] }) =>
      api.submitHumanReview(reviewId, {
        grade: payload.grade,
        notes: payload.notes,
        frames: payload.frames.map((f) => ({ frameId: f.id, note: f.note, overrides: buildFrameOverrides(f.items) })),
      }),
    [reviewId],
  );

  if (failed) {
    return (
      <div style={{ height: "100%", display: "grid", placeItems: "center", background: "var(--bg)" }}>
        <div style={{ textAlign: "center", color: "var(--ink-3)" }}>
          <Ico name="alert" size={28} stroke="var(--red)" />
          <p style={{ marginTop: 10, fontSize: 13 }}>{t("review.loaderr")}</p>
          <Btn kind="default" size="sm" icon="arrowL" onClick={onExit} style={{ marginTop: 12 }}>{t("review.back")}</Btn>
        </div>
      </div>
    );
  }
  if (!model) {
    return (
      <div style={{ height: "100%", display: "grid", placeItems: "center", background: "var(--bg)", color: "var(--ink-3)" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13 }}>
          <Ico name="refresh" size={16} style={{ animation: "evas-spin 1s linear infinite" }} /> {t("common.loading")}…
        </span>
      </div>
    );
  }
  return <ReviewWorkbench key={reviewId} {...props} review={model} mediaUrl={mediaUrl} live={isLive} onPersist={persist} />;
}

function ReviewWorkbench({
  t,
  reviewId,
  qaMode,
  onExit,
  onSubmitted,
  session,
  soundOn,
  onToggleSound,
  review,
  mediaUrl,
  live,
  onPersist,
}: ReviewScreenProps & {
  review: Review;
  mediaUrl: string | null;
  live: boolean;
  onPersist: (p: { grade: number; notes: string; frames: Frame[] }) => Promise<unknown>;
}) {
  const totalDur = review.frames[review.frames.length - 1].t + 2;

  const [frames, setFrames] = useState<Frame[]>(() => review.frames.map((f) => ({ ...f, items: f.items.map((i) => ({ ...i })) })));
  const [flaggedFirst, setFlaggedFirst] = useState(true);
  const [selectedId, setSelectedId] = useState(review.frames[0].id);
  const [curItem, setCurItem] = useState(0);
  const [vGrade, setVGrade] = useState<number | null>(null);
  const [gradeEdited, setGradeEdited] = useState(false);
  const [vNotes, setVNotes] = useState("");
  const [showHelp, setShowHelp] = useState(false);
  const [confirmDlg, setConfirmDlg] = useState(false);
  const [flash, setFlash] = useState<{ m: string; action?: { label: string; fn: () => void } } | null>(null);
  const [playing, setPlaying] = useState(false);
  const [, setHistory] = useState<{ frames: Frame[]; label: string }[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [saved, setSaved] = useState(true);

  const [kbdUses, setKbdUses] = useState(() => +(localStorage.getItem("evas-kbd-uses") || 0));
  const [hintHover, setHintHover] = useState(false);
  const hintOpacity = hintHover ? 1 : kbdUses > 70 ? 0.22 : kbdUses > 30 ? 0.5 : 1;
  function bumpKbd() {
    setKbdUses((n) => {
      const v = n + 1;
      localStorage.setItem("evas-kbd-uses", String(v));
      return v;
    });
  }

  const gradeRef = useRef<HTMLInputElement>(null);
  const stripRef = useRef<HTMLDivElement>(null);
  const savedTimer = useRef<number | undefined>(undefined);
  const flashTimer = useRef<number | undefined>(undefined);
  function markSaved() {
    setSaved(false);
    clearTimeout(savedTimer.current);
    savedTimer.current = window.setTimeout(() => setSaved(true), 550);
  }

  const qaOriginal = useMemo(() => {
    if (!qaMode) return null;
    const m: Record<string, string[]> = {};
    frames.forEach((f) => {
      m[f.id] = f.items.map((it) => (Math.random() > 0.82 ? (it.expect === "Yes" ? "No" : "Yes") : it.aiValue));
    });
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qaMode, reviewId]);

  const displayFrames = useMemo(() => {
    if (!flaggedFirst) return frames;
    return [...frames].sort((a, b) => Number(b.flagged) - Number(a.flagged) || a.idx - b.idx);
  }, [frames, flaggedFirst]);

  const selIndexDisplay = displayFrames.findIndex((f) => f.id === selectedId);
  const selected = frames.find((f) => f.id === selectedId)!;

  const reviewedCount = frames.filter((f) => f.items.some((i) => i.state !== "pending")).length;
  const overridesCount = frames.reduce((s, f) => s + f.items.filter((i) => i.state.startsWith("override")).length, 0);
  const flaggedFrames = frames.filter((f) => f.flagged);
  const flaggedUntouched = flaggedFrames.filter((f) => !f.items.some((i) => i.state !== "pending"));
  const canSubmit = flaggedUntouched.length === 0;

  const derivedGrade = useMemo(() => {
    let pen = 0;
    frames.forEach((f) =>
      f.items.forEach((it) => {
        const fin = it.state === "override-yes" ? "Yes" : it.state === "override-no" ? "No" : it.aiValue;
        if (fin !== it.expect) pen += it.risk ? 2.0 : 1.0;
      }),
    );
    let g = 10 - pen * 0.28;
    g = Math.max(0, Math.min(10, g));
    return Math.round(g * 2) / 2;
  }, [frames]);
  const effGrade = gradeEdited && vGrade != null ? vGrade : derivedGrade;

  const agreement = useMemo(() => {
    if (!qaMode || !qaOriginal) return null;
    let same = 0,
      total = 0;
    frames.forEach((f) =>
      f.items.forEach((it, i) => {
        if (it.state === "pending") return;
        total++;
        const mine = it.state === "override-yes" ? "Yes" : it.state === "override-no" ? "No" : it.aiValue;
        if (mine === qaOriginal[f.id][i]) same++;
      }),
    );
    return total ? Math.round((same / total) * 100) : null;
  }, [frames, qaMode, qaOriginal]);

  function flashMsg(m: string, action?: { label: string; fn: () => void }) {
    setFlash(action ? { m, action } : { m });
    clearTimeout(flashTimer.current);
    flashTimer.current = window.setTimeout(() => setFlash(null), action ? 3200 : 1400);
  }

  function playTick() {
    if (!soundOn) return;
    try {
      const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      audioCtx = audioCtx || new Ctx();
      const ac = audioCtx;
      const o = ac.createOscillator(),
        g = ac.createGain();
      o.type = "sine";
      o.frequency.value = 660;
      o.connect(g);
      g.connect(ac.destination);
      const now = ac.currentTime;
      g.gain.setValueAtTime(0.0001, now);
      g.gain.exponentialRampToValueAtTime(0.06, now + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, now + 0.12);
      o.start(now);
      o.stop(now + 0.13);
    } catch {
      /* no-op */
    }
  }

  const selectFrame = useCallback((id: string) => {
    setSelectedId(id);
    setCurItem(0);
  }, []);
  function moveFrame(delta: number) {
    const ni = Math.max(0, Math.min(displayFrames.length - 1, selIndexDisplay + delta));
    selectFrame(displayFrames[ni].id);
  }
  function nextFlagged() {
    for (let k = 1; k <= displayFrames.length; k++) {
      const f = displayFrames[(selIndexDisplay + k) % displayFrames.length];
      if (f.flagged) {
        selectFrame(f.id);
        flashMsg("→ flagged frame " + (f.idx + 1));
        return;
      }
    }
    flashMsg("✓ no flagged frames left");
  }
  function pushHistory(label: string) {
    setHistory((h) => [...h.slice(-30), { frames, label }]);
    markSaved();
  }
  function undo() {
    setHistory((h) => {
      if (!h.length) {
        flashMsg("nothing to undo");
        return h;
      }
      const last = h[h.length - 1];
      setFrames(last.frames);
      flashMsg("↩ undone");
      markSaved();
      return h.slice(0, -1);
    });
  }
  function setItem(frameId: string, idx: number, state: ItemState) {
    pushHistory("item");
    setFrames((prev) => prev.map((f) => (f.id !== frameId ? f : { ...f, items: f.items.map((it, i) => (i === idx ? { ...it, state } : it)) })));
  }
  function actCurrent(state: ItemState) {
    if (!selected || curItem >= selected.items.length) return;
    setItem(selected.id, curItem, state);
    if (state === "confirmed") playTick();
    setCurItem((c) => Math.min(selected.items.length - 1, c + 1));
  }
  function confirmAllFrame(id: string) {
    pushHistory("frame");
    setFrames((prev) => prev.map((f) => (f.id !== id ? f : { ...f, items: f.items.map((it) => ({ ...it, state: it.state === "pending" ? "confirmed" : it.state })) })));
    playTick();
    flashMsg("✓ frame confirmed", { label: t("erg.undo"), fn: undo });
  }
  function confirmRemainingUnflagged() {
    pushHistory("bulk");
    setFrames((prev) => prev.map((f) => (f.flagged ? f : { ...f, items: f.items.map((it) => ({ ...it, state: it.state === "pending" ? "confirmed" : it.state })) })));
    setConfirmDlg(false);
    playTick();
    flashMsg("✓ all unflagged frames confirmed", { label: t("erg.undo"), fn: undo });
  }
  function submit() {
    if (!canSubmit) {
      flashMsg("⚠ touch all flagged frames first");
      return;
    }
    if (submitting) return;
    setSubmitting(true);
    playTick();
    const result = { ref: review.ref, grade: effGrade, overrides: overridesCount, reviewed: reviewedCount, total: frames.length, agreement };
    // Live, non-QA reviews write through the human-review API (assign → frame
    // overrides → grade + complete). QA and mock reviews keep the local flow.
    if (live && !qaMode) {
      onPersist({ grade: effGrade, notes: vNotes, frames })
        .then(() => onSubmitted(result))
        .catch((e: unknown) => {
          setSubmitting(false);
          flashMsg("⚠ submit failed: " + (e instanceof Error ? e.message : String(e)));
        });
    } else {
      setTimeout(() => onSubmitted(result), 640);
    }
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = ((e.target as HTMLElement).tagName || "").toUpperCase();
      const typing = tag === "INPUT" || tag === "TEXTAREA";
      if (typing) {
        if (e.key === "Enter" && e.target === gradeRef.current) {
          e.preventDefault();
          (e.target as HTMLInputElement).blur();
          submit();
        }
        if (e.key === "Escape") (e.target as HTMLElement).blur();
        return;
      }
      if (submitting) return;
      if (confirmDlg) {
        if (e.key === "Enter") confirmRemainingUnflagged();
        if (e.key === "Escape") setConfirmDlg(false);
        return;
      }
      if (showHelp && e.key === "Escape") {
        setShowHelp(false);
        return;
      }
      const k = e.key;
      const handled = () => {
        e.preventDefault();
        bumpKbd();
      };
      if (k === "ArrowRight") {
        handled();
        moveFrame(1);
      } else if (k === "ArrowLeft") {
        handled();
        moveFrame(-1);
      } else if (k === "f" || k === "F") {
        handled();
        nextFlagged();
      } else if (k === "c" || k === "C") {
        handled();
        actCurrent("confirmed");
      } else if (k === "y" || k === "Y") {
        handled();
        actCurrent("override-yes");
      } else if (k === "n" || k === "N") {
        handled();
        actCurrent("override-no");
      } else if (k === "z" || k === "Z") {
        handled();
        undo();
      } else if (k === "a" && !e.shiftKey) {
        handled();
        confirmAllFrame(selectedId);
      } else if (k === "A" && e.shiftKey) {
        handled();
        setConfirmDlg(true);
      } else if (k === "g" || k === "G") {
        handled();
        gradeRef.current?.focus();
      } else if (k === "?") {
        handled();
        setShowHelp((s) => !s);
      } else if (/^[0-9]$/.test(k)) {
        handled();
        const idx = k === "0" ? 9 : parseInt(k, 10) - 1;
        if (selected && idx < selected.items.length) setCurItem(idx);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  useLayoutEffect(() => {
    const strip = stripRef.current;
    if (!strip) return;
    const el = strip.querySelector(`[data-fid="${selectedId}"]`) as HTMLElement | null;
    if (el) {
      const l = el.offsetLeft,
        r = l + el.offsetWidth;
      if (l < strip.scrollLeft + 8) strip.scrollLeft = l - 12;
      else if (r > strip.scrollLeft + strip.clientWidth - 8) strip.scrollLeft = r - strip.clientWidth + 12;
    }
  }, [selectedId, flaggedFirst]);

  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => {
      setSelectedId((cur) => {
        const i = frames.findIndex((f) => f.id === cur);
        if (i >= frames.length - 1) {
          setPlaying(false);
          return cur;
        }
        return frames[i + 1].id;
      });
    }, 700);
    return () => clearInterval(id);
  }, [playing, frames]);

  const sceneMeta = sceneOf(review.scene);

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", background: "var(--bg)" }}>
      {qaMode && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 18px", background: "var(--violet)", color: "white", fontSize: 12.5, fontWeight: 550 }}>
          <Ico name="shield" size={15} />
          {t("review.qamode")} <strong>Marco Díaz</strong>
          <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6, opacity: 0.95 }}>
            {t("review.agreement")}: <span className="mono tnum" style={{ fontWeight: 700 }}>{agreement == null ? "—" : agreement + "%"}</span>
          </span>
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "10px 18px", borderBottom: "1px solid var(--line)", background: "var(--panel)", flexShrink: 0 }}>
        <Btn kind="ghost" size="sm" icon="arrowL" onClick={onExit}>{t("review.back")}</Btn>
        <div style={{ width: 1, height: 20, background: "var(--line)" }} />
        <span className="mono" style={{ fontWeight: 600, fontSize: 14, whiteSpace: "nowrap", flexShrink: 0 }}>{review.ref}</span>
        <ClientChip client={review.client} />
        <span className="label" style={{ padding: "3px 7px", background: "var(--panel-3)", borderRadius: 3 }}>{sceneMeta.label}</span>

        {session && (
          <div style={{ margin: "0 auto", display: "flex", alignItems: "center", gap: 11 }} title="Today's session">
            <span className="label" style={{ fontSize: 9.5 }}>{t("erg.session")}</span>
            <div style={{ width: 150, height: 6, borderRadius: 99, background: "var(--panel-3)", overflow: "hidden", border: "1px solid var(--line)" }}>
              <div style={{ width: `${Math.min(100, (session.reviewedToday / session.target) * 100)}%`, height: "100%", background: "var(--green)", transition: "width .5s cubic-bezier(.2,.6,.2,1)" }} />
            </div>
            <span className="mono tnum" style={{ fontSize: 11.5, color: "var(--ink-2)" }}>
              <b style={{ color: "var(--ink)" }}>{session.reviewedToday}</b> / {session.target} {t("erg.today")}
            </span>
            {session.streak >= 3 && (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 3, fontSize: 11, color: "var(--amber)", fontWeight: 600 }} title={`${session.streak} in a row`}>
                <Ico name="bolt" size={12} fill="var(--amber)" stroke="none" />{session.streak}
              </span>
            )}
          </div>
        )}

        <div style={{ marginLeft: session ? 0 : "auto", display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, color: "var(--ink-4)", transition: "color .2s", width: 58 }}>
            <Ico name={saved ? "check" : "refresh"} size={12} style={!saved ? { animation: "evas-spin 1s linear infinite" } : undefined} />
            {saved ? t("erg.saved") : "…"}
          </span>
          <button onClick={onToggleSound} title={t("erg.sound")} style={{ width: 30, height: 30, borderRadius: 5, border: "1px solid var(--line)", background: soundOn ? "var(--accent-2)" : "var(--panel)", display: "grid", placeItems: "center", color: soundOn ? "var(--accent)" : "var(--ink-3)" }}>
            <Ico name={soundOn ? "volume" : "volumeOff"} size={15} />
          </button>
          <Btn kind="ghost" size="sm" onClick={() => setShowHelp((s) => !s)}>
            <kbd>?</kbd> {t("review.shortcuts")}
          </Btn>
        </div>
      </div>

      <div style={{ flex: 1, display: "grid", gridTemplateColumns: "minmax(230px,21%) 1fr minmax(248px,22%)", minHeight: 0 }}>
        {/* LEFT RAIL */}
        <aside style={{ borderRight: "1px solid var(--line)", display: "flex", flexDirection: "column", background: "var(--panel)", overflow: "auto", minHeight: 0 }}>
          <div style={{ padding: 14 }}>
            <div className="label" style={{ marginBottom: 8, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span>{t("review.context")}</span>
              {mediaUrl && (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: "var(--accent)", fontSize: 9.5, letterSpacing: "0.04em" }}>
                  <Ico name="play" size={11} /> {t("review.fullvideo")}
                </span>
              )}
            </div>
            {mediaUrl ? (
              <video
                src={mediaUrl}
                controls
                playsInline
                preload="metadata"
                style={{ width: "100%", aspectRatio: "16/10", borderRadius: 3, background: "#000", display: "block" }}
              />
            ) : (
              <FrameThumb frame={selected} large style={{ width: "100%", aspectRatio: "16/10" }} />
            )}
            <div style={{ marginTop: 8 }}>
              <div
                onClick={(e) => {
                  const r = e.currentTarget.getBoundingClientRect();
                  const pct = (e.clientX - r.left) / r.width;
                  let best = frames[0];
                  frames.forEach((f) => {
                    if (Math.abs(f.t / totalDur - pct) < Math.abs(best.t / totalDur - pct)) best = f;
                  });
                  selectFrame(best.id);
                }}
                style={{ position: "relative", height: 8, background: "var(--panel-3)", borderRadius: 99, cursor: "pointer", border: "1px solid var(--line)" }}
              >
                <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${(selected.t / totalDur) * 100}%`, background: "var(--accent)", borderRadius: 99, opacity: 0.35 }} />
                {frames.filter((f) => f.flagged).map((f) => (
                  <div key={f.id} style={{ position: "absolute", top: -1, bottom: -1, width: 2, borderRadius: 2, left: `${(f.t / totalDur) * 100}%`, background: "var(--amber)" }} />
                ))}
                <div style={{ position: "absolute", top: "50%", left: `${(selected.t / totalDur) * 100}%`, width: 12, height: 12, borderRadius: 99, background: "var(--accent)", border: "2px solid var(--panel)", transform: "translate(-50%,-50%)", boxShadow: "var(--shadow-1)" }} />
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
                <Btn kind="default" size="sm" icon={playing ? "pause" : "play"} onClick={() => setPlaying((p) => !p)} style={{ padding: "5px 8px" }} />
                <span className="mono tnum" style={{ fontSize: 11, color: "var(--ink-2)" }}>{selected.timecode}</span>
                <span className="mono" style={{ fontSize: 11, color: "var(--ink-4)", marginLeft: "auto" }}>{review.duration}</span>
              </div>
            </div>
          </div>

          <div style={{ borderTop: "1px solid var(--line-2)", padding: 14, display: "flex", flexDirection: "column", gap: 11 }}>
            <Meta label={t("review.client")}><ClientChip client={review.client} /></Meta>
            <Meta label={t("review.ref")}><span className="mono">{review.ref}</span></Meta>
            <Meta label={t("review.duration")}><span className="mono">{review.duration} · {frames.length} frames</span></Meta>
            <Meta label={t("review.checklist")}>
              <span>{review.checklist.name} <span className="mono" style={{ color: "var(--ink-3)" }}>{review.checklist.version}</span></span>
            </Meta>
            <Meta label={t("review.aigrade")}>
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Grade value={review.aiGrade} size={18} />
                <span className="mono" style={{ fontSize: 10, color: "var(--ink-4)" }}>{review.model} · {review.promptVersion}</span>
              </span>
            </Meta>
          </div>
          <div style={{ borderTop: "1px solid var(--line-2)", padding: 14, marginTop: "auto" }}>
            <div className="label" style={{ marginBottom: 6 }}>{t("review.summary")}</div>
            <p style={{ margin: 0, fontSize: 12.5, color: "var(--ink-2)", lineHeight: 1.55 }}>{review.aiSummary}</p>
          </div>
        </aside>

        {/* CENTER */}
        <main style={{ display: "flex", flexDirection: "column", minHeight: 0, overflow: "hidden" }}>
          <div style={{ borderBottom: "1px solid var(--line)", background: "var(--panel)", flexShrink: 0 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 14px 4px" }}>
              <div className="label">{t("review.frame")}S · <span style={{ color: "var(--ink-2)" }}>{frames.length}</span></div>
              <button onClick={() => setFlaggedFirst((v) => !v)} style={{ display: "flex", alignItems: "center", gap: 7, border: "none", background: "transparent", fontSize: 12, color: "var(--ink-2)", fontWeight: 500 }}>
                <span style={{ position: "relative", width: 30, height: 17, borderRadius: 99, background: flaggedFirst ? "var(--amber)" : "var(--line-strong)", transition: "background .15s" }}>
                  <span style={{ position: "absolute", top: 2, left: flaggedFirst ? 15 : 2, width: 13, height: 13, borderRadius: 99, background: "white", transition: "left .15s", boxShadow: "var(--shadow-1)" }} />
                </span>
                <Ico name="flag" size={13} fill={flaggedFirst ? "var(--amber)" : "none"} stroke={flaggedFirst ? "none" : "var(--ink-3)"} />
                {t("review.flaggedfirst")}
              </button>
            </div>
            <div ref={stripRef} style={{ display: "flex", gap: 7, overflowX: "auto", padding: "4px 14px 12px" }}>
              {displayFrames.map((f) => {
                const isSel = f.id === selectedId;
                const touched = f.items.some((i) => i.state !== "pending");
                return (
                  <button key={f.id} data-fid={f.id} onClick={() => selectFrame(f.id)} style={{ flexShrink: 0, padding: 0, border: "none", background: "transparent", cursor: "pointer", position: "relative" }}>
                    <FrameThumb frame={f} style={{ width: 92, height: 56, outline: isSel ? "2px solid var(--accent)" : "1px solid var(--line)", opacity: !isSel && touched ? 0.62 : 1, transition: "opacity .12s" }} showHud={false} />
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 4, marginTop: 3 }}>
                      {f.flagged && <span style={{ width: 5, height: 5, borderRadius: 99, background: "var(--amber)" }} />}
                      {touched && <Ico name="check" size={11} stroke="var(--green)" sw={2.4} />}
                      <span className="mono tnum" style={{ fontSize: 9.5, color: isSel ? "var(--accent)" : "var(--ink-4)", fontWeight: isSel ? 600 : 400 }}>{f.timecode}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div style={{ flex: 1, overflow: "auto", minHeight: 0, padding: "16px 18px 28px" }}>
            <div style={{ display: "grid", gridTemplateColumns: "minmax(300px, 1.05fr) 1.35fr", gap: 18, alignItems: "start" }}>
              <div>
                <FrameThumb frame={selected} large style={{ width: "100%", aspectRatio: "16/10", boxShadow: "var(--shadow-2)" }} />
                <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "10px 0 6px" }}>
                  <span className="label">{t("review.frame")} {selected.idx + 1}/{frames.length}</span>
                  {selected.flagged && (
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10.5, fontWeight: 600, whiteSpace: "nowrap", color: "var(--amber)", background: "var(--amber-bg)", padding: "2px 6px", borderRadius: 3 }}>
                      <Ico name="flag" size={11} fill="var(--amber)" stroke="none" /> FLAGGED · low confidence
                    </span>
                  )}
                </div>
                <div className="label" style={{ marginBottom: 4 }}>{t("review.aidesc")}</div>
                <p style={{ margin: "0 0 14px", fontSize: 13.5, color: "var(--ink)", lineHeight: 1.55 }}>{selected.desc}</p>
                <div className="label" style={{ marginBottom: 5 }}>{t("review.note")}</div>
                <input
                  defaultValue={selected.note}
                  key={selected.id}
                  placeholder={t("review.noteph")}
                  onChange={markSaved}
                  onBlur={(e) => setFrames((prev) => prev.map((f) => (f.id === selected.id ? { ...f, note: e.target.value } : f)))}
                  style={{ width: "100%", padding: "8px 11px", borderRadius: 4, border: "1px solid var(--line-strong)", background: "var(--panel-2)", fontSize: 13, outline: "none" }}
                />
              </div>

              <div>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                  <span className="label">{review.checklist.name} · {selected.items.length} items</span>
                  <Btn kind="default" size="sm" onClick={() => confirmAllFrame(selected.id)} icon="check">
                    Confirm all <kbd style={{ marginLeft: 4 }}>a</kbd>
                  </Btn>
                </div>
                <div className="panel" style={{ overflow: "hidden" }}>
                  {selected.items.map((it, i) => (
                    <ChecklistRow key={it.key} item={it} index={i} active={i === curItem} onFocus={() => setCurItem(i)} t={t} qaVal={qaOriginal ? qaOriginal[selected.id][i] : null} onSet={(st) => { setItem(selected.id, i, st); setCurItem(Math.min(selected.items.length - 1, i + 1)); }} last={i === selected.items.length - 1} />
                  ))}
                </div>
                <div style={{ display: "flex", gap: 14, marginTop: 10, flexWrap: "wrap", color: "var(--ink-4)", fontSize: 11, opacity: hintOpacity, transition: "opacity .4s", cursor: "default" }} onMouseEnter={() => setHintHover(true)} onMouseLeave={() => setHintHover(false)} title={t("erg.hintsfade")}>
                  <span><kbd>1</kbd>–<kbd>0</kbd> jump item</span>
                  <span><kbd>c</kbd> confirm</span>
                  <span><kbd>y</kbd>/<kbd>n</kbd> override</span>
                  <span><kbd>a</kbd> confirm frame</span>
                  <span><kbd>f</kbd> next flagged</span>
                  <span><kbd>z</kbd> undo</span>
                </div>
              </div>
            </div>
          </div>
        </main>

        {/* RIGHT RAIL */}
        <aside style={{ borderLeft: "1px solid var(--line)", background: "var(--panel)", display: "flex", flexDirection: "column", overflow: "auto", minHeight: 0 }}>
          <div style={{ padding: 16 }}>
            <div className="label" style={{ marginBottom: 12 }}>{t("review.verdict")}</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 1, background: "var(--line)", border: "1px solid var(--line)", borderRadius: 5, overflow: "hidden", marginBottom: 14 }}>
              <Stat label={t("review.reviewed")} value={`${reviewedCount}/${frames.length}`} />
              <Stat label={t("review.overrides")} value={overridesCount} tone={overridesCount > 0 ? "var(--amber)" : null} />
            </div>
            <div style={{ height: 6, borderRadius: 99, background: "var(--panel-3)", overflow: "hidden", marginBottom: 4 }}>
              <div style={{ width: `${(reviewedCount / frames.length) * 100}%`, height: "100%", background: "var(--accent)", transition: "width .25s" }} />
            </div>
            <div style={{ fontSize: 11, color: "var(--ink-3)", marginBottom: 18 }}>{flaggedFrames.length} flagged · {flaggedUntouched.length} untouched</div>

            <div className="label" style={{ marginBottom: 7, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span>{t("review.grade")}</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: "var(--accent)", fontSize: 9, padding: "2px 5px", background: "var(--accent-2)", borderRadius: 3, letterSpacing: "0.06em" }}>{t("review.derived").toUpperCase()}</span>
            </div>
            <div style={{ display: "flex", alignItems: "stretch", gap: 8, marginBottom: 6 }}>
              <input ref={gradeRef} type="number" min="0" max="10" step="0.5" value={effGrade} onChange={(e) => { setGradeEdited(true); setVGrade(Math.max(0, Math.min(10, parseFloat(e.target.value) || 0))); }} style={{ flex: 1, padding: "10px 12px", borderRadius: 4, border: "1px solid var(--line-strong)", background: "var(--panel-2)", fontFamily: '"IBM Plex Mono", monospace', fontSize: 22, fontWeight: 600, textAlign: "center", outline: "none", color: effGrade >= 8 ? "var(--green)" : effGrade >= 5.5 ? "var(--amber)" : "var(--red)" }} />
              <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", gap: 3 }}>
                {gradeEdited && (
                  <button onClick={() => { setGradeEdited(false); flashMsg("↺ reset to derived"); }} style={{ fontSize: 10, color: "var(--ink-3)", background: "none", border: "1px solid var(--line)", borderRadius: 3, padding: "3px 6px" }}>reset</button>
                )}
                <span className="mono" style={{ fontSize: 10, color: "var(--ink-4)", whiteSpace: "nowrap" }}>0–10</span>
                <span className="mono" style={{ fontSize: 10, color: "var(--ink-4)", whiteSpace: "nowrap" }}>±0.5</span>
              </div>
            </div>
            <div style={{ fontSize: 11, color: "var(--ink-4)", marginBottom: 16 }}>
              Computed default <span className="mono" style={{ color: "var(--ink-2)" }}>{derivedGrade.toFixed(1)}</span> · press <kbd>g</kbd> to edit
            </div>

            <div className="label" style={{ marginBottom: 7 }}>{t("review.vnotes")}</div>
            <textarea value={vNotes} onChange={(e) => { setVNotes(e.target.value); markSaved(); }} placeholder={t("review.vnotesph")} rows={4} style={{ width: "100%", padding: "9px 11px", borderRadius: 4, border: "1px solid var(--line-strong)", background: "var(--panel-2)", fontSize: 12.5, resize: "vertical", outline: "none", lineHeight: 1.5 }} />
          </div>

          <div style={{ marginTop: "auto", padding: 16, borderTop: "1px solid var(--line)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 10, fontSize: 12, color: canSubmit ? "var(--green)" : "var(--amber)" }}>
              <Ico name={canSubmit ? "check" : "alert"} size={14} />
              {canSubmit ? t("review.ready") : `${flaggedUntouched.length} ${t("review.flagleft")}`}
            </div>
            <Btn kind="primary" size="lg" onClick={submit} disabled={!canSubmit} style={{ width: "100%", justifyContent: "center" }}>
              {t("review.submit")} <kbd style={{ marginLeft: 6, background: "rgba(255,255,255,0.18)", borderColor: "transparent", color: "inherit" }}>↵</kbd>
            </Btn>
            <div style={{ textAlign: "center", fontSize: 10.5, color: "var(--ink-4)", marginTop: 8 }}>
              <kbd>⇧A</kbd> confirm all remaining unflagged
            </div>
          </div>
        </aside>
      </div>

      {flash && (
        <div className="fade-in" style={{ position: "fixed", bottom: 22, left: "50%", transform: "translateX(-50%)", background: "var(--ink)", color: "var(--bg)", padding: "9px 10px 9px 16px", borderRadius: 8, fontSize: 13, fontWeight: 550, boxShadow: "var(--shadow-pop)", zIndex: 60, display: "flex", alignItems: "center", gap: 12 }}>
          <span>{flash.m}</span>
          {flash.action && (
            <button onClick={() => { flash.action!.fn(); setFlash(null); }} style={{ display: "inline-flex", alignItems: "center", gap: 5, border: "none", background: "var(--accent)", color: "var(--accent-ink)", padding: "5px 10px", borderRadius: 5, fontSize: 12, fontWeight: 600 }}>
              <Ico name="undo" size={13} /> {flash.action.label}
            </button>
          )}
        </div>
      )}

      {submitting && (
        <div style={{ position: "absolute", inset: 0, zIndex: 90, display: "grid", placeItems: "center", background: "color-mix(in oklab, var(--bg) 78%, transparent)", backdropFilter: "blur(2px)" }}>
          <div style={{ textAlign: "center", animation: "evas-sweep .64s cubic-bezier(.2,.7,.2,1) both" }}>
            <div style={{ width: 64, height: 64, borderRadius: 99, margin: "0 auto", background: "var(--green-bg)", display: "grid", placeItems: "center" }}>
              <Ico name="check" size={34} stroke="var(--green)" sw={2.6} />
            </div>
            <div className="mono" style={{ marginTop: 12, fontSize: 13, color: "var(--ink-2)", fontWeight: 600 }}>{review.ref} · {effGrade.toFixed(1)}</div>
          </div>
        </div>
      )}

      {confirmDlg && (
        <Modal onClose={() => setConfirmDlg(false)}>
          <h3 style={{ fontSize: 16, marginBottom: 8 }}>Confirm all remaining unflagged frames?</h3>
          <p style={{ color: "var(--ink-2)", fontSize: 13, lineHeight: 1.55, marginBottom: 18 }}>
            This accepts every AI finding on the <strong>{frames.filter((f) => !f.flagged && f.items.some((i) => i.state === "pending")).length}</strong> unflagged frames that you haven't touched. Flagged frames still require your judgement.
          </p>
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <Btn kind="default" onClick={() => setConfirmDlg(false)}>Cancel <kbd style={{ marginLeft: 4 }}>esc</kbd></Btn>
            <Btn kind="primary" icon="check" onClick={confirmRemainingUnflagged}>Confirm all <kbd style={{ marginLeft: 4, background: "rgba(255,255,255,0.18)", borderColor: "transparent" }}>↵</kbd></Btn>
          </div>
        </Modal>
      )}

      {showHelp && <ShortcutsHelp t={t} onClose={() => setShowHelp(false)} />}
    </div>
  );
}

function ChecklistRow({ item, index, active, onSet, onFocus, last, t, qaVal }: { item: Frame["items"][number]; index: number; active: boolean; onSet: (s: ItemState) => void; onFocus: () => void; last: boolean; t: TFn; qaVal: string | null }) {
  const confirmed = item.state === "confirmed";
  const ovY = item.state === "override-yes",
    ovN = item.state === "override-no";
  const overridden = ovY || ovN;
  const mismatch = item.aiValue !== item.expect;
  return (
    <div onClick={onFocus} style={{ position: "relative", padding: confirmed ? "7px 12px" : "10px 12px", borderBottom: last ? "none" : "1px solid var(--line-2)", cursor: "pointer", background: active ? "var(--accent-2)" : overridden ? "var(--amber-bg)" : "transparent", transition: "background .12s, padding .12s", boxShadow: active ? "inset 2px 0 0 var(--accent)" : overridden ? "inset 2px 0 0 var(--amber)" : "none" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span className="mono" style={{ fontSize: 10, width: 16, height: 16, borderRadius: 3, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 600, background: active ? "var(--accent)" : "var(--panel-3)", color: active ? "var(--accent-ink)" : "var(--ink-3)" }}>{index === 9 ? 0 : index + 1}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 6 }}>
            <span style={{ fontSize: confirmed ? 12 : 13, fontWeight: 500, minWidth: 0, lineHeight: 1.3, overflowWrap: "anywhere", color: confirmed ? "var(--ink-3)" : "var(--ink)" }}>{item.label}</span>
            {item.risk && <Ico name="shield" size={12} stroke="var(--violet)" style={{ flexShrink: 0, marginTop: 2 }} />}
          </div>
          {!confirmed && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 5 }}>
              <span className="mono" style={{ fontSize: 10.5, padding: "1px 6px", borderRadius: 3, fontWeight: 600, flexShrink: 0, whiteSpace: "nowrap", background: mismatch ? "var(--red-bg)" : "var(--panel-3)", color: mismatch ? "var(--red)" : "var(--ink-2)" }}>AI: {item.aiValue}</span>
              <div style={{ flexShrink: 0 }}><ConfBar v={item.conf} width={46} /></div>
              {qaVal != null && <span className="mono" style={{ fontSize: 10, color: "var(--violet)", flexShrink: 0 }}>R: {qaVal}</span>}
            </div>
          )}
        </div>
        {confirmed ? (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 5, color: "var(--green)", fontSize: 11.5, fontWeight: 600, flexShrink: 0 }}>
            <Ico name="check" size={14} sw={2.4} /> {item.aiValue}
          </span>
        ) : (
          <div style={{ display: "flex", gap: 3, flexShrink: 0 }}>
            <Tri icon="check" label={t("review.confirm") + " (c)"} tone="var(--green)" active={false} onClick={(e) => { e.stopPropagation(); onSet("confirmed"); }} />
            <Tri label="Y" tone="var(--accent)" active={ovY} onClick={(e) => { e.stopPropagation(); onSet("override-yes"); }} />
            <Tri label="N" tone="var(--red)" active={ovN} onClick={(e) => { e.stopPropagation(); onSet("override-no"); }} />
          </div>
        )}
      </div>
    </div>
  );
}

function Tri({ label, icon, tone, active, onClick }: { label: string; icon?: string; tone: string; active: boolean; onClick: (e: React.MouseEvent) => void }) {
  return (
    <button onClick={onClick} title={label} style={{ minWidth: 30, height: 27, padding: "0 8px", borderRadius: 4, fontSize: 11.5, fontWeight: 600, border: `1px solid ${active ? tone : "var(--line-strong)"}`, background: active ? tone : "var(--panel)", color: active ? "white" : icon ? "var(--green)" : "var(--ink-2)", display: "inline-flex", alignItems: "center", justifyContent: "center", transition: "all .1s" }}>
      {icon ? <Ico name={icon} size={15} sw={2.4} /> : label}
    </button>
  );
}

function ShortcutsHelp({ t, onClose }: { t: TFn; onClose: () => void }) {
  const rows = [
    ["→ / ←", "Next / previous frame"],
    ["f", "Next flagged frame"],
    ["1 … 9, 0", "Jump to checklist item 1–10"],
    ["c", "Confirm current item"],
    ["y / n", "Override yes / no"],
    ["a", "Confirm all AI findings on frame"],
    ["⇧ A", "Confirm all remaining unflagged frames"],
    ["z", "Undo last action"],
    ["g", "Focus grade input"],
    ["↵", "Submit review (from grade)"],
    ["?", "Toggle this panel"],
  ];
  return (
    <Modal onClose={onClose}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <h3 style={{ fontSize: 16 }}>{t("review.shortcuts")}</h3>
        <button onClick={onClose} style={{ border: "none", background: "transparent", color: "var(--ink-3)" }}><Ico name="x" size={18} /></button>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {rows.map(([k, d], i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "7px 0", borderBottom: i < rows.length - 1 ? "1px solid var(--line-2)" : "none" }}>
            <span style={{ fontSize: 13, color: "var(--ink-2)" }}>{d}</span>
            <span style={{ display: "flex", gap: 4 }}>
              {k.split(" ").map((p, j) => (p === "/" || p === "…" || p === "," ? <span key={j} style={{ color: "var(--ink-4)", alignSelf: "center" }}>{p}</span> : <kbd key={j}>{p}</kbd>))}
            </span>
          </div>
        ))}
      </div>
    </Modal>
  );
}
