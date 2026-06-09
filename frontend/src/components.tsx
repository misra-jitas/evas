// Shared UI primitives, icons, and atoms — the "instrument-panel" kit.
// Ported verbatim (visually) from the design prototype; inline styles + theme.css
// custom properties drive the look, so this matches the mock pixel-for-pixel.
import React from "react";
import { createPortal } from "react-dom";
import type { Client, FrameItem, Source, TFn } from "./types";

type CSS = React.CSSProperties;

/* ---------------- Icons (inline, 1.6 stroke) ---------------- */
export const IC: Record<string, string | string[]> = {
  play: "M8 5.5v13l11-6.5z",
  pause: ["M9 5v14", "M15 5v14"],
  chevR: "M9 6l6 6-6 6",
  chevL: "M15 6l-6 6 6 6",
  chevD: "M6 9l6 6 6-6",
  chevU: "M6 15l6-6 6 6",
  arrowR: "M5 12h14M13 6l6 6-6 6",
  arrowL: "M19 12H5M11 6l-6 6 6 6",
  check: "M5 12.5l4.5 4.5L19 7",
  x: "M6 6l12 12M18 6L6 18",
  flag: ["M5 21V4", "M5 4h11l-2 4 2 4H5"],
  search: ["M11 11m-7 0a7 7 0 1 0 14 0a7 7 0 1 0-14 0", "M20 20l-3.5-3.5"],
  sun: ["M12 12m-4 0a4 4 0 1 0 8 0a4 4 0 1 0-8 0", "M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4"],
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
  grid: ["M4 4h7v7H4z", "M13 4h7v7h-7z", "M4 13h7v7H4z", "M13 13h7v7h-7z"],
  list: ["M8 6h12", "M8 12h12", "M8 18h12", "M4 6h.01M4 12h.01M4 18h.01"],
  layers: ["M12 3l9 5-9 5-9-5 9-5z", "M3 13l9 5 9-5"],
  dollar: ["M12 3v18", "M16.5 7.5C16.5 5.8 14.5 5 12 5S7.5 6 7.5 8 9.5 11 12 11s4.5 1 4.5 3-2 3-4.5 3-4.5-.8-4.5-2.5"],
  activity: "M3 12h4l3 8 4-16 3 8h4",
  alert: ["M12 9v4", "M12 17h.01", "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"],
  film: ["M4 4h16v16H4z", "M8 4v16M16 4v16M4 8h4M4 12h4M4 16h4M16 8h4M16 12h4M16 16h4"],
  user: ["M12 12m-4 0a4 4 0 1 0 8 0a4 4 0 1 0-8 0", "M5 20a7 7 0 0 1 14 0"],
  eye: ["M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z", "M12 12m-3 0a3 3 0 1 0 6 0a3 3 0 1 0-6 0"],
  download: ["M12 3v12", "M7 11l5 5 5-5", "M4 21h16"],
  refresh: ["M21 12a9 9 0 1 1-3-6.7", "M21 4v4h-4"],
  clock: ["M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0-18 0", "M12 7v5l3 2"],
  zap: "M13 2 4 14h7l-1 8 9-12h-7l1-8z",
  logout: ["M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4", "M16 17l5-5-5-5", "M21 12H9"],
  shield: ["M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z"],
  dot: "M12 12m-3 0a3 3 0 1 0 6 0a3 3 0 1 0-6 0",
  filter: "M3 5h18l-7 8v6l-4 2v-8z",
  hash: ["M4 9h16M4 15h16", "M10 3 8 21M16 3l-2 18"],
  database: ["M12 5c4.4 0 8-1.1 8-2.5S16.4 0 12 0 4 1.1 4 2.5 7.6 5 12 5z", "M4 2.5v15C4 19 7.6 20 12 20s8-1 8-2.5v-15", "M4 10c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5"],
  link: ["M9 15l6-6", "M11 6l1-1a4 4 0 0 1 6 6l-2 2", "M13 18l-1 1a4 4 0 0 1-6-6l2-2"],
  cpu: ["M6 6h12v12H6z", "M10 10h4v4h-4z", "M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3"],
  plus: ["M12 5v14", "M5 12h14"],
  kebab: ["M12 6h.01", "M12 12h.01", "M12 18h.01"],
  undo: ["M9 14l-4-4 4-4", "M5 10h11a4 4 0 0 1 0 8h-1"],
  volume: ["M11 5L6 9H2v6h4l5 4z", "M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"],
  volumeOff: ["M11 5L6 9H2v6h4l5 4z", "M22 9l-6 6M16 9l6 6"],
  coffee: ["M4 8h13v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5z", "M17 9h2a2 2 0 0 1 0 4h-2", "M7 2v2M10 2v2M13 2v2"],
  award: ["M12 12m-6 0a6 6 0 1 0 12 0a6 6 0 1 0-12 0", "M9 17l-1 5 4-2 4 2-1-5"],
  sliders: ["M4 8h10M18 8h2", "M4 16h2M10 16h10", "M14 6v4M6 14v4"],
  power: ["M12 3v9", "M6.6 6.6a9 9 0 1 0 10.8 0"],
  bolt: "M13 2 4 14h7l-1 8 9-12h-7l1-8z",
  pulse: "M3 12h4l2-7 4 14 2-7h6",
  eyeOff: ["M2 2l20 20", "M6.7 6.7A10 10 0 0 0 2 12s3.5 7 10 7a9.8 9.8 0 0 0 5.3-1.5", "M9.9 5.2A10 10 0 0 1 12 5c6.5 0 10 7 10 7a16 16 0 0 1-2.2 3.1"],
};

export function Icon({
  d,
  paths,
  size = 16,
  fill,
  stroke = "currentColor",
  sw = 1.6,
  style,
}: {
  d?: string;
  paths?: string[];
  size?: number;
  fill?: string;
  stroke?: string;
  sw?: number;
  style?: CSS;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={fill || "none"}
      stroke={fill ? "none" : stroke}
      strokeWidth={sw}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ flexShrink: 0, ...style }}
    >
      {d && <path d={d} />}
      {paths && paths.map((p, i) => <path key={i} d={p} />)}
    </svg>
  );
}

export function Ico({ name, ...rest }: { name: string } & Omit<Parameters<typeof Icon>[0], "d" | "paths">) {
  const v = IC[name];
  if (Array.isArray(v)) return <Icon paths={v} {...rest} />;
  return <Icon d={v} {...rest} />;
}

/* ---------------- Egocentric POV frame placeholder ---------------- */
export interface ThumbFrame {
  hue: number;
  timecode?: string;
  flagged?: boolean;
}
export function FrameThumb({
  frame,
  large,
  style,
  showHud = true,
}: {
  frame: ThumbFrame;
  large?: boolean;
  style?: CSS;
  showHud?: boolean;
}) {
  const h = frame.hue;
  const sky = `oklch(0.62 0.07 ${h})`;
  const ground = `oklch(0.34 0.05 ${h + 8})`;
  const horizon = large ? "46%" : "50%";
  return (
    <div
      style={{
        position: "relative",
        overflow: "hidden",
        borderRadius: 3,
        background: `linear-gradient(${ground} 0%, oklch(0.42 0.05 ${h}) ${horizon}, ${sky} ${horizon}, oklch(0.7 0.06 ${h}) 100%)`,
        ...style,
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: `radial-gradient(120% 90% at 50% 55%, transparent 52%, oklch(0.1 0.02 ${h} / 0.55) 100%)`,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: "50%",
          bottom: large ? -28 : -14,
          width: large ? 220 : 70,
          height: large ? 120 : 40,
          transform: "translateX(-50%)",
          borderRadius: "50% 50% 0 0",
          background: `oklch(0.4 0.06 ${h + 20} / 0.85)`,
          filter: "blur(0.5px)",
        }}
      />
      {showHud && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            padding: large ? "12px 14px" : "5px 6px",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            fontFamily: '"IBM Plex Mono", monospace',
            color: "oklch(0.97 0 0)",
            pointerEvents: "none",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: large ? 11 : 8, textShadow: "0 1px 2px rgba(0,0,0,.6)" }}>
              <span className="rec-dot" style={{ width: large ? 7 : 5, height: large ? 7 : 5, borderRadius: 99, background: "oklch(0.62 0.23 25)", display: "inline-block" }} />
              REC
            </span>
            <span style={{ fontSize: large ? 11 : 8, textShadow: "0 1px 2px rgba(0,0,0,.6)" }}>{frame.timecode}</span>
          </div>
          {large && (
            <div style={{ alignSelf: "center", width: 26, height: 26, border: "1.5px solid oklch(0.97 0 0 / 0.7)", borderRadius: 99, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <div style={{ width: 3, height: 3, borderRadius: 99, background: "oklch(0.97 0 0 / 0.9)" }} />
            </div>
          )}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", fontSize: large ? 10 : 7 }}>
            <span style={{ textShadow: "0 1px 2px rgba(0,0,0,.6)", opacity: 0.9, whiteSpace: "nowrap" }}>{large ? "POV · 1440p · 30fps" : ""}</span>
          </div>
        </div>
      )}
      {frame.flagged && (
        <div
          style={{
            position: "absolute",
            top: large ? 12 : 4,
            ...(large ? { right: 44 } : { right: 4 }),
            width: large ? 9 : 7,
            height: large ? 9 : 7,
            borderRadius: 99,
            background: "var(--amber)",
            boxShadow: "0 0 0 2px oklch(0.1 0 0 / 0.3)",
          }}
        />
      )}
    </div>
  );
}

/* ---------------- Small atoms ---------------- */
export function PriorityBadge({ p }: { p: "rush" | "high" | "normal" }) {
  const map = {
    rush: { bg: "var(--red-bg)", fg: "var(--red)", label: "RUSH" },
    high: { bg: "var(--amber-bg)", fg: "var(--amber)", label: "HIGH" },
    normal: { bg: "var(--panel-3)", fg: "var(--ink-3)", label: "NORM" },
  };
  const m = map[p];
  return (
    <span className="mono" style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.06em", padding: "2px 6px", borderRadius: 3, background: m.bg, color: m.fg, display: "inline-flex", alignItems: "center", gap: 4 }}>
      {p === "rush" && <span style={{ width: 5, height: 5, borderRadius: 99, background: "var(--red)" }} />}
      {m.label}
    </span>
  );
}

export function Grade({ value, size = 13, muted }: { value: number | null; size?: number; muted?: boolean }) {
  if (value == null) return <span className="mono" style={{ color: "var(--ink-4)", fontSize: size }}>—</span>;
  const tone = value >= 8 ? "var(--green)" : value >= 5.5 ? "var(--amber)" : "var(--red)";
  return (
    <span className="mono tnum" style={{ fontSize: size, fontWeight: 600, color: muted ? "var(--ink-2)" : tone }}>
      {value.toFixed(1)}
    </span>
  );
}

export function ConfBar({ v, width = 54 }: { v: number; width?: number }) {
  const tone = v >= 0.75 ? "var(--green)" : v >= 0.55 ? "var(--amber)" : "var(--red)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ width, height: 4, borderRadius: 99, background: "var(--line)", overflow: "hidden" }}>
        <div style={{ width: `${v * 100}%`, height: "100%", background: tone, borderRadius: 99 }} />
      </div>
      <span className="mono tnum" style={{ fontSize: 10, color: "var(--ink-3)", width: 24 }}>{Math.round(v * 100)}</span>
    </div>
  );
}

type BtnKind = "default" | "primary" | "ghost" | "danger";
type BtnSize = "sm" | "md" | "lg";
export function Btn({
  children,
  kind = "default",
  size = "md",
  icon,
  onClick,
  disabled,
  style,
  ...rest
}: {
  children?: React.ReactNode;
  kind?: BtnKind;
  size?: BtnSize;
  icon?: string;
  style?: CSS;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const sizes: Record<BtnSize, CSS> = {
    sm: { padding: "5px 9px", fontSize: 12, gap: 5 },
    md: { padding: "8px 13px", fontSize: 13, gap: 6 },
    lg: { padding: "11px 18px", fontSize: 14, gap: 7 },
  };
  const kinds: Record<BtnKind, CSS> = {
    default: { background: "var(--panel)", color: "var(--ink)", border: "1px solid var(--line-strong)" },
    primary: { background: "var(--accent)", color: "var(--accent-ink)", border: "1px solid var(--accent)" },
    ghost: { background: "transparent", color: "var(--ink-2)", border: "1px solid transparent" },
    danger: { background: "var(--red-bg)", color: "var(--red)", border: "1px solid transparent" },
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        ...sizes[size],
        borderRadius: 4,
        fontWeight: 550,
        whiteSpace: "nowrap",
        transition: "background .12s, border-color .12s, opacity .12s, transform .06s",
        opacity: disabled ? 0.45 : 1,
        cursor: disabled ? "not-allowed" : "pointer",
        ...kinds[kind],
        ...style,
      }}
      onMouseDown={(e) => !disabled && (e.currentTarget.style.transform = "translateY(0.5px)")}
      onMouseUp={(e) => (e.currentTarget.style.transform = "none")}
      onMouseLeave={(e) => (e.currentTarget.style.transform = "none")}
      {...rest}
    >
      {icon && <Ico name={icon} size={size === "lg" ? 17 : 15} />}
      {children}
    </button>
  );
}

export function ClientChip({ client, mono }: { client: Client; mono?: boolean }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 7, minWidth: 0 }}>
      <span style={{ width: 18, height: 18, borderRadius: 3, background: client.tint, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 8, fontWeight: 700, color: "white", fontFamily: '"IBM Plex Mono", monospace', letterSpacing: "0.02em" }}>
        {client.short.slice(0, 2)}
      </span>
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontFamily: mono ? '"IBM Plex Mono", monospace' : "inherit", fontSize: mono ? 12 : 13 }}>
        {client.name}
      </span>
    </span>
  );
}

export function Spark({ data, w = 90, h = 26, tone = "var(--accent)" }: { data: number[]; w?: number; h?: number; tone?: string }) {
  const min = Math.min(...data);
  const max = Math.max(...data);
  const pts = data.map((d, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - 3 - ((d - min) / (max - min || 1)) * (h - 6);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const last = pts[pts.length - 1].split(",");
  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      <polyline points={pts.join(" ")} fill="none" stroke={tone} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={last[0]} cy={last[1]} r="2" fill={tone} />
    </svg>
  );
}

export interface SegmentOption {
  value: string;
  label: string;
  icon?: string;
}
export function Segment({ options, value, onChange, size = "sm" }: { options: SegmentOption[]; value: string; onChange: (v: string) => void; size?: "sm" | "md" }) {
  return (
    <div style={{ display: "inline-flex", padding: 2, background: "var(--panel-3)", borderRadius: 5, border: "1px solid var(--line)" }}>
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 5,
            padding: size === "sm" ? "4px 9px" : "6px 12px",
            fontSize: 12,
            fontWeight: 550,
            borderRadius: 4,
            border: "none",
            background: value === o.value ? "var(--panel)" : "transparent",
            color: value === o.value ? "var(--ink)" : "var(--ink-3)",
            boxShadow: value === o.value ? "var(--shadow-1)" : "none",
            transition: "all .12s",
          }}
        >
          {o.icon && <Ico name={o.icon} size={14} />}
          {o.label}
        </button>
      ))}
    </div>
  );
}

/* ---------------- Colorblind-safe status badge ----------------
   Never color alone: every status carries a distinct ICON + label. */
export const STATUS_TOKENS: Record<string, { c: string; bg: string; icon: string; label: string; spin?: boolean }> = {
  connected: { c: "var(--green)", bg: "var(--green-bg)", icon: "check", label: "Connected" },
  syncing: { c: "var(--accent)", bg: "var(--accent-2)", icon: "refresh", label: "Syncing", spin: true },
  error: { c: "var(--red)", bg: "var(--red-bg)", icon: "alert", label: "Error" },
  disabled: { c: "var(--ink-4)", bg: "var(--panel-3)", icon: "power", label: "Disabled" },
  running: { c: "var(--accent)", bg: "var(--accent-2)", icon: "pulse", label: "Running" },
  queued: { c: "var(--ink-3)", bg: "var(--panel-3)", icon: "clock", label: "Queued" },
  completed: { c: "var(--green)", bg: "var(--green-bg)", icon: "check", label: "Completed" },
  failed: { c: "var(--red)", bg: "var(--red-bg)", icon: "alert", label: "Failed" },
  dead: { c: "var(--red)", bg: "var(--red-bg)", icon: "x", label: "Dead" },
  reviewed: { c: "var(--green)", bg: "var(--green-bg)", icon: "check", label: "Reviewed" },
  in_review: { c: "var(--amber)", bg: "var(--amber-bg)", icon: "eye", label: "In review" },
  processing: { c: "var(--ink-3)", bg: "var(--panel-3)", icon: "refresh", label: "Processing", spin: true },
  ai_graded: { c: "var(--accent)", bg: "var(--accent-2)", icon: "cpu", label: "AI graded" },
};
export function StatusBadge({ status, label, size = "md", solid }: { status: string; label?: string; size?: "sm" | "md"; solid?: boolean }) {
  const s = STATUS_TOKENS[status] || STATUS_TOKENS.queued;
  const fs = size === "sm" ? 10.5 : 11.5;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: fs, fontWeight: 600, color: s.c, background: solid ? "transparent" : s.bg, padding: solid ? 0 : "3px 9px", borderRadius: 99, width: "fit-content", whiteSpace: "nowrap" }}>
      <Ico name={s.icon} size={size === "sm" ? 11 : 12.5} sw={2} style={s.spin ? { animation: "evas-spin 1.4s linear infinite" } : undefined} />
      {label || s.label}
    </span>
  );
}

/* ---------------- Funnel bar (sources) ---------------- */
export function FunnelBar({ src, height = 9, showLegend }: { src: Source; height?: number; showLegend?: boolean }) {
  const segs = [
    { k: "done", v: src.done, c: "var(--green)", t: "solid", label: "done" },
    { k: "inReview", v: src.inReview, c: "var(--amber)", t: "diag", label: "in review" },
    { k: "ingested", v: src.ingested, c: "var(--accent)", t: "solid", label: "ingested" },
    { k: "failed", v: src.failed, c: "var(--red)", t: "cross", label: "failed" },
    { k: "toGo", v: src.toGo, c: "var(--line-strong)", t: "empty", label: "to ingest" },
  ].filter((s) => s.v > 0);
  const total = src.total || 1;
  return (
    <div>
      <div style={{ display: "flex", height, borderRadius: 99, overflow: "hidden", background: "var(--panel-3)", border: "1px solid var(--line)" }}>
        {total === 0 ? (
          <div style={{ flex: 1, display: "grid", placeItems: "center" }} />
        ) : (
          segs.map((s, i) => (
            <div
              key={s.k}
              title={`${s.v} ${s.label}`}
              style={{
                width: `${(s.v / total) * 100}%`,
                background: s.c,
                backgroundImage:
                  s.t === "diag"
                    ? "repeating-linear-gradient(45deg, rgba(255,255,255,.28) 0 3px, transparent 3px 6px)"
                    : s.t === "cross"
                      ? "repeating-linear-gradient(45deg, rgba(255,255,255,.35) 0 2px, transparent 2px 5px)"
                      : s.t === "empty"
                        ? "repeating-linear-gradient(90deg, var(--line) 0 1px, transparent 1px 5px)"
                        : "none",
                borderRight: i < segs.length - 1 ? "1px solid var(--panel)" : "none",
              }}
            />
          ))
        )}
      </div>
      {showLegend && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 14px", marginTop: 8 }}>
          {([["done", src.done, "var(--green)"], ["in review", src.inReview, "var(--amber)"], ["ingested", src.ingested, "var(--accent)"], ["queued", src.toGo, "var(--ink-3)"], ["failed", src.failed, "var(--red)"]] as const).map(([l, v, c]) => (
            <span key={l} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11.5, color: "var(--ink-2)" }}>
              <span style={{ width: 8, height: 8, borderRadius: 2, background: c, flexShrink: 0 }} />
              <span className="mono tnum" style={{ fontWeight: 600, color: "var(--ink)" }}>{v}</span> {l}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------------- Shared layout atoms ---------------- */
export function Modal({ children, onClose, wide }: { children: React.ReactNode; onClose: () => void; wide?: boolean }) {
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "oklch(0.15 0.02 265 / 0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 80, animation: "evas-fade .15s both", padding: 20 }}>
      <div onClick={(e) => e.stopPropagation()} className="panel" style={{ maxWidth: wide ? 540 : 420, width: "100%", padding: 22, maxHeight: "90vh", overflow: "auto", boxShadow: "var(--shadow-pop)", animation: "evas-pop .18s both" }}>
        {children}
      </div>
    </div>
  );
}

export function Stat({ label, value, tone }: { label: string; value: React.ReactNode; tone?: string | null }) {
  return (
    <div style={{ background: "var(--panel)", padding: "10px 12px" }}>
      <div className="label" style={{ marginBottom: 3 }}>{label}</div>
      <div className="mono tnum" style={{ fontSize: 19, fontWeight: 600, color: tone || "var(--ink)" }}>{value}</div>
    </div>
  );
}

export function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <span className="label">{label}</span>
      <div style={{ fontSize: 13 }}>{children}</div>
    </div>
  );
}

export function Row({ children, cols, head, last, onClick, style }: { children: React.ReactNode; cols: string; head?: boolean; last?: boolean; onClick?: () => void; style?: CSS }) {
  const kids = React.Children.toArray(children);
  return (
    <div
      onClick={onClick}
      style={{
        display: "grid",
        gridTemplateColumns: cols,
        gap: 12,
        alignItems: "center",
        padding: head ? "9px 14px" : "10px 14px",
        background: head ? "var(--panel-2)" : "transparent",
        borderBottom: head ? "1px solid var(--line)" : last ? "none" : "1px solid var(--line-2)",
        cursor: onClick ? "pointer" : "default",
        ...style,
      }}
      onMouseEnter={onClick ? (e) => (e.currentTarget.style.background = "var(--panel-2)") : undefined}
      onMouseLeave={onClick ? (e) => (e.currentTarget.style.background = "transparent") : undefined}
    >
      {kids}
    </div>
  );
}

export interface SelectOption {
  v: string;
  l: string;
}
export function Select({ value, onChange, options, icon, full }: { value: string; onChange: (v: string) => void; options: SelectOption[]; icon?: string; full?: boolean }) {
  return (
    <span style={{ position: "relative", display: full ? "block" : "inline-flex", alignItems: "center", width: full ? "100%" : undefined }}>
      {icon && <Ico name={icon} size={14} stroke="var(--ink-3)" style={{ position: "absolute", left: 9, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }} />}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{ appearance: "none", width: full ? "100%" : undefined, padding: icon ? "8px 26px 8px 28px" : "8px 26px 8px 11px", borderRadius: 4, border: "1px solid var(--line-strong)", background: "var(--panel)", fontSize: 12.5, color: "var(--ink)", cursor: "pointer", outline: "none" }}
      >
        {options.map((o) => (
          <option key={o.v} value={o.v}>{o.l}</option>
        ))}
      </select>
      <Ico name="chevD" size={13} stroke="var(--ink-3)" style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }} />
    </span>
  );
}

export function EmptyState({ icon, title, sub, action }: { icon: string; title: string; sub?: string; action?: React.ReactNode }) {
  return (
    <div className="grid-tex panel" style={{ display: "grid", placeItems: "center", minHeight: 260, textAlign: "center", padding: 40 }}>
      <div style={{ maxWidth: 340 }}>
        <div style={{ width: 48, height: 48, borderRadius: 9, margin: "0 auto 16px", display: "grid", placeItems: "center", background: "var(--panel)", border: "1px solid var(--line)", color: "var(--ink-3)" }}>
          <Ico name={icon} size={23} />
        </div>
        <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 6 }}>{title}</div>
        {sub && <div style={{ color: "var(--ink-3)", fontSize: 13, lineHeight: 1.55 }}>{sub}</div>}
        {action && <div style={{ marginTop: 18, display: "flex", justifyContent: "center" }}>{action}</div>}
      </div>
    </div>
  );
}

export function EmptyInline({ icon, msg }: { icon: string; msg: string }) {
  return (
    <div style={{ padding: "26px 14px", textAlign: "center", color: "var(--ink-4)", fontSize: 13, display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
      <Ico name={icon} size={22} stroke="var(--ink-4)" /> {msg}
    </div>
  );
}

export const fieldInput: CSS = { padding: "9px 11px", borderRadius: 5, border: "1px solid var(--line-strong)", background: "var(--panel-2)", fontSize: 13, outline: "none", width: "100%" };

export function Field({ label, hint, children }: { label: string; hint?: string | null; children: React.ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <span className="label">{label}</span>
      {children}
      {hint && <span style={{ fontSize: 11, color: "var(--amber)" }}>{hint}</span>}
    </label>
  );
}

export function Toggle({ on, onChange }: { on: boolean; onChange: () => void }) {
  return (
    <button onClick={(e) => { e.preventDefault(); onChange(); }} style={{ position: "relative", width: 38, height: 22, borderRadius: 99, border: "none", flexShrink: 0, background: on ? "var(--accent)" : "var(--line-strong)", transition: "background .15s" }}>
      <span style={{ position: "absolute", top: 3, left: on ? 19 : 3, width: 16, height: 16, borderRadius: 99, background: "white", transition: "left .15s", boxShadow: "var(--shadow-1)" }} />
    </button>
  );
}

export function Avatar({ initials }: { initials: string }) {
  return (
    <span style={{ width: 22, height: 22, borderRadius: 99, background: "var(--panel-3)", border: "1px solid var(--line)", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 9.5, fontWeight: 600, color: "var(--ink-2)", flexShrink: 0 }}>{initials}</span>
  );
}

export function BarCell({ v, max, tone, fmt }: { v: number; max: number; tone: string; fmt: (x: number) => string }) {
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ flex: 1, height: 5, borderRadius: 99, background: "var(--line)", overflow: "hidden", maxWidth: 70 }}>
        <span style={{ display: "block", width: `${Math.min(100, (v / max) * 100)}%`, height: "100%", background: tone, borderRadius: 99 }} />
      </span>
      <span className="mono tnum" style={{ fontSize: 12, width: 34 }}>{fmt(v)}</span>
    </span>
  );
}

export function SearchBox({ q, setQ, t }: { q: string; setQ: (s: string) => void; t: TFn }) {
  return (
    <span style={{ position: "relative", display: "inline-flex", alignItems: "center" }}>
      <Ico name="search" size={15} stroke="var(--ink-4)" style={{ position: "absolute", left: 10, pointerEvents: "none" }} />
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("common.search")} style={{ padding: "8px 12px 8px 32px", borderRadius: 4, border: "1px solid var(--line-strong)", background: "var(--panel)", fontSize: 13, width: 240, outline: "none" }} />
    </span>
  );
}

export function Dotsep() {
  return <span style={{ color: "var(--line-strong)" }}>·</span>;
}

export function Tag({ label, value }: { label: string; value: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "4px 9px", borderRadius: 4, background: "var(--panel-3)", border: "1px solid var(--line)" }}>
      <span className="label" style={{ fontSize: 9 }}>{label}</span>
      <span className="mono" style={{ fontSize: 11.5, fontWeight: 600 }}>{value}</span>
    </span>
  );
}

export function Legend({ c, l }: { c: string; l: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
      <span style={{ width: 8, height: 8, borderRadius: 2, background: c }} />
      {l}
    </span>
  );
}

export function CostLine({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5 }}>
      <span style={{ color: "var(--ink-3)" }}>{label}</span>
      <span className="mono tnum" style={{ fontWeight: 600 }}>{value}</span>
    </div>
  );
}

export function Kebab({ items }: { items: { label: string; icon: string; danger?: boolean; onClick?: () => void }[] }) {
  const [open, setOpen] = React.useState(false);
  const [coords, setCoords] = React.useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const btnRef = React.useRef<HTMLButtonElement>(null);
  const MENU_W = 150;

  // Position the menu from the button's viewport rect (fixed) so it is never
  // clipped by an ancestor's overflow:hidden (e.g. a table panel). Flips up
  // when there isn't room below.
  const place = React.useCallback(() => {
    const r = btnRef.current?.getBoundingClientRect();
    if (!r) return;
    const estH = items.length * 36 + 10;
    const below = r.bottom + 6;
    const top = below + estH > window.innerHeight ? Math.max(8, r.top - estH - 6) : below;
    const left = Math.max(8, Math.min(r.right - MENU_W, window.innerWidth - MENU_W - 8));
    setCoords({ top, left });
  }, [items.length]);

  React.useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    window.addEventListener("click", close);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  return (
    <span style={{ position: "relative" }} onClick={(e) => e.stopPropagation()}>
      <button
        ref={btnRef}
        onClick={() => {
          if (!open) place();
          setOpen((o) => !o);
        }}
        style={{ width: 30, height: 30, borderRadius: 5, border: "1px solid var(--line)", background: "var(--panel)", display: "grid", placeItems: "center", color: "var(--ink-3)" }}
      >
        <Ico name="kebab" size={16} />
      </button>
      {open &&
        createPortal(
          <div className="panel" style={{ position: "fixed", top: coords.top, left: coords.left, width: MENU_W, padding: 5, zIndex: 1000, boxShadow: "var(--shadow-pop)", animation: "evas-pop .13s both" }} onClick={(e) => e.stopPropagation()}>
            {items.map((it) => (
              <button
                key={it.label}
                onClick={() => { setOpen(false); it.onClick?.(); }}
                style={{ display: "flex", alignItems: "center", gap: 9, width: "100%", padding: "8px 10px", border: "none", background: "transparent", borderRadius: 4, fontSize: 12.5, color: it.danger ? "var(--red)" : "var(--ink-2)", textAlign: "left" }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--panel-2)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
              >
                <Ico name={it.icon} size={14} /> {it.label}
              </button>
            ))}
          </div>,
          document.body,
        )}
    </span>
  );
}

/** confidence helper used by the Review checklist + AI drill-down */
export function minConf(items: FrameItem[]): number {
  return items.length ? Math.min(...items.map((i) => i.conf)) : 0;
}
