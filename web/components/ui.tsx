"use client";

import { marked } from "marked";
import { useEffect, useMemo, useRef } from "react";
import type { Loadable } from "@/lib/data";
import { label, pct } from "@/lib/format";

export function Chip({ tone, children }: { tone: "pass" | "warn" | "fail" | "off"; children: React.ReactNode }) {
  return <span className={`chip chip-${tone}`}>{children}</span>;
}

export function verdictTone(verdict: string): "pass" | "warn" | "off" {
  if (verdict.startsWith("confirmed")) return "pass";
  if (verdict.startsWith("supported")) return "warn";
  return "off";
}

export function statusTone(status: string): "pass" | "warn" | "fail" | "off" {
  if (status === "approved" || status === "pass") return "pass";
  if (status === "pending_approval" || status === "not_measured") return "warn";
  if (status.startsWith("rejected") || status === "fail") return "fail";
  return "off";
}

export function PageHead({ title, lede, children }: { title: string; lede?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className="page-head">
      <h1 className="page-title">{title}</h1>
      {lede && <p className="page-lede">{lede}</p>}
      {children}
    </div>
  );
}

export function Load<T>({ value, children }: { value: Loadable<T>; children: (data: T) => React.ReactNode }) {
  if (value.state === "loading") return <div className="empty">Loading the export…</div>;
  if (value.state === "error")
    return (
      <div className="empty">
        The export file is missing ({value.message}). Run{" "}
        <code className="mono">fdeops demo --export web/public/demo</code> and reload.
      </div>
    );
  return <>{children(value.data)}</>;
}

/** Markdown from the platform's own reports. Raw HTML in the source is shown as text. */
export function Markdown({ source }: { source: string }) {
  const html = useMemo(() => {
    const escaped = source.replace(/</g, "&lt;");
    return marked.parse(escaped, { async: false, gfm: true }) as string;
  }, [source]);
  return <div className="md" dangerouslySetInnerHTML={{ __html: html }} />;
}

/** A rate with its confidence interval on a 0 to 100% track. */
export function IntervalBar({ value, lo, hi }: { value: number; lo: number; hi: number }) {
  return (
    <div className="bar-track" role="img" aria-label={`${pct(value)} (95% CI ${pct(lo)} to ${pct(hi)})`}>
      <div className="bar-ci" style={{ left: `${lo * 100}%`, width: `${Math.max(0.6, (hi - lo) * 100)}%` }} />
      <div className="bar-point" style={{ left: `calc(${value * 100}% - 1.5px)` }} />
    </div>
  );
}

export function Drawer({ open, onClose, children }: { open: boolean; onClose: () => void; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    ref.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <>
      <div className="scrim" onClick={onClose} aria-hidden />
      <div className="drawer" role="dialog" aria-modal="true" tabIndex={-1} ref={ref}>
        {children}
      </div>
    </>
  );
}

export function Tabs<T extends string>({ value, options, onChange }: { value: T; options: readonly T[]; onChange: (v: T) => void }) {
  return (
    <div className="tabs" role="tablist">
      {options.map((o) => (
        <button key={o} type="button" role="tab" className="tab" aria-selected={o === value} onClick={() => onChange(o)}>
          {label(o)}
        </button>
      ))}
    </div>
  );
}
