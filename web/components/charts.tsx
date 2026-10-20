"use client";

import type { DiffEstimate, Distribution } from "@/lib/types";
import { label, money, pct, signed } from "@/lib/format";

/**
 * Forest plot: each row is a paired difference (B minus A) with its 95% interval. The zero line is
 * "no change". A row whose interval does not cross zero is a credible change.
 */
export function ForestPlot({
  rows,
  pvals,
}: {
  rows: [string, DiffEstimate][];
  pvals?: Record<string, number>;
}) {
  const width = 760;
  const left = 230;
  const right = 120;
  const rowH = 30;
  const raw = Math.max(0.25, ...rows.flatMap(([, d]) => [Math.abs(d.lo), Math.abs(d.hi)])) * 1.1;
  const lim = Math.ceil(raw * 10) / 10;
  const tickStep = lim <= 0.4 ? 0.1 : lim <= 1 ? 0.2 : 0.5;
  const x = (v: number) => left + ((v + lim) / (2 * lim)) * (width - left - right);
  const height = rows.length * rowH + 40;
  const n = Math.floor(lim / tickStep + 1e-9);
  const ticks = Array.from({ length: 2 * n + 1 }, (_, i) => Math.round((i - n) * tickStep * 100) / 100);
  return (
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Paired differences with 95% intervals">
      {ticks.map((t) => (
        <g key={t}>
          <line className={t === 0 ? "zero" : "grid"} x1={x(t)} x2={x(t)} y1={8} y2={height - 26} />
          <text x={x(t)} y={height - 8} textAnchor="middle">
            {signed(t, 2)}
          </text>
        </g>
      ))}
      {rows.map(([name, d], i) => {
        const y = 22 + i * rowH;
        const credible = d.hi < 0 || d.lo > 0;
        const color = !credible ? "var(--ink-3)" : d.mean < 0 ? "var(--lamp-fail)" : "var(--lamp-pass)";
        return (
          <g key={name}>
            <text className="label" x={left - 12} y={y + 4} textAnchor="end">
              {label(name)}
            </text>
            <line className="whisker" x1={x(d.lo)} x2={x(d.hi)} y1={y} y2={y} stroke={color} style={{ animationDelay: `${i * 30}ms` }} />
            <rect x={x(d.mean) - 4} y={y - 4} width={8} height={8} fill={color} transform={`rotate(45 ${x(d.mean)} ${y})`} />
            <text x={width - right + 10} y={y + 4}>
              {signed(d.mean, 2)}
              {pvals?.[name] !== undefined ? `  p=${pvals[name]!.toFixed(3)}` : ""}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** Several runs on one 0 to 100% ruler, each with its interval. */
export function RunRuler({ runs }: { runs: { name: string; value: number; lo: number; hi: number; tone: string }[] }) {
  const width = 760;
  const left = 190;
  const right = 70;
  const rowH = 34;
  const height = runs.length * rowH + 36;
  const x = (v: number) => left + v * (width - left - right);
  return (
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Task success of each run with 95% intervals">
      {[0, 0.25, 0.5, 0.75, 1].map((t) => (
        <g key={t}>
          <line className="grid" x1={x(t)} x2={x(t)} y1={6} y2={height - 24} />
          <text x={x(t)} y={height - 6} textAnchor="middle">
            {pct(t, 0)}
          </text>
        </g>
      ))}
      {runs.map((r, i) => {
        const y = 22 + i * rowH;
        return (
          <g key={r.name}>
            <text className="label" x={left - 12} y={y + 4} textAnchor="end">
              {r.name}
            </text>
            <line className="whisker" x1={x(r.lo)} x2={x(r.hi)} y1={y} y2={y} stroke={r.tone} style={{ animationDelay: `${i * 40}ms` }} />
            <circle cx={x(r.value)} cy={y} r={5} fill={r.tone} />
            <text x={width - right + 8} y={y + 4}>
              {pct(r.value)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** A distribution as a band: 5th to 95th percentile, with the median. */
export function PercentileBands({ rows, format = money }: { rows: [string, Distribution][]; format?: (x: number) => string }) {
  const width = 760;
  const left = 300;
  const right = 20;
  const rowH = 44;
  const finite = rows.flatMap(([, d]) => [d.p5, d.p95]).filter(Number.isFinite);
  const lo = Math.min(0, ...finite);
  const hi = Math.max(...finite, 1);
  const x = (v: number) => left + ((v - lo) / (hi - lo || 1)) * (width - left - right);
  const height = rows.length * rowH + 16;
  return (
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Percentile bands">
      {lo < 0 && <line className="zero" x1={x(0)} x2={x(0)} y1={4} y2={height - 6} />}
      {rows.map(([name, d], i) => {
        const y = 20 + i * rowH;
        const neg = d.p50 < 0;
        return (
          <g key={name}>
            <text className="label" x={left - 12} y={y + 4} textAnchor="end">
              {name}
            </text>
            <rect className="whisker" x={x(d.p5)} y={y - 7} width={Math.max(2, x(d.p95) - x(d.p5))} height={14} rx={2}
              fill={neg ? "color-mix(in srgb, var(--lamp-fail) 28%, transparent)" : "color-mix(in srgb, var(--lamp-pass) 28%, transparent)"} />
            <line x1={x(d.p50)} x2={x(d.p50)} y1={y - 10} y2={y + 10} stroke="var(--ink)" strokeWidth={2.5} />
            <text x={x(d.p50)} y={y + 24} textAnchor="middle">
              {format(d.p50)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/**
 * The current window as a strip of tickets, in traffic order. A lit tick is a ticket with the flag.
 * The marker is the ticket where the sequential detector (CUSUM) gave its alarm.
 */
export function TicketStrip({ flags, alarmAt, tone }: { flags: boolean[]; alarmAt: number | null; tone: string }) {
  const width = 760;
  const height = 46;
  const step = (width - 8) / Math.max(1, flags.length);
  const w = Math.max(1.5, Math.min(8, step - 1.5));
  return (
    <svg className="chart strip" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${flags.filter(Boolean).length} of ${flags.length} tickets flagged${alarmAt ? `, alarm at ticket ${alarmAt}` : ""}`}>
      <line className="grid" x1={4} x2={width - 4} y1={30} y2={30} />
      {flags.map((f, i) => (
        <rect key={i} className="tick" x={4 + i * step} y={f ? 12 : 26} width={w} height={f ? 18 : 4} rx={1} fill={f ? tone : "var(--rule)"} style={{ animationDelay: `${i * 6}ms` }} />
      ))}
      {alarmAt && (
        <g>
          <line className="alarm" x1={4 + (alarmAt - 1) * step + w / 2} x2={4 + (alarmAt - 1) * step + w / 2} y1={2} y2={36} />
          <text x={Math.min(width - 90, 4 + (alarmAt - 1) * step + w / 2 + 6)} y={44}>
            alarm · ticket {alarmAt}
          </text>
        </g>
      )}
    </svg>
  );
}

/** A change with its 95% interval against zero and the tolerance. An alert is an interval past the tolerance. */
export function ToleranceBar({ lo, hi, change, tolerance, alert }: { lo: number; hi: number; change: number; tolerance: number; alert: boolean }) {
  const width = 220;
  const height = 22;
  const lim = Math.max(0.05, Math.abs(lo), Math.abs(hi), tolerance) * 1.1;
  const x = (v: number) => 6 + ((v + lim) / (2 * lim)) * (width - 12);
  const color = alert ? "var(--lamp-fail)" : "var(--ink-3)";
  return (
    <svg className="chart tol" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`change ${signed(change, 3)}, interval ${signed(lo, 3)} to ${signed(hi, 3)}, tolerance ${signed(tolerance, 3)}`}>
      <rect className="tol-zone" x={x(tolerance)} y={3} width={Math.max(0, width - 6 - x(tolerance))} height={height - 6} />
      <line className="zero" x1={x(0)} x2={x(0)} y1={2} y2={height - 2} />
      <line className="tol-line" x1={x(tolerance)} x2={x(tolerance)} y1={2} y2={height - 2} />
      <line x1={x(lo)} x2={x(hi)} y1={height / 2} y2={height / 2} stroke={color} strokeWidth={2.5} strokeLinecap="round" />
      <circle cx={x(change)} cy={height / 2} r={3.5} fill={color} />
    </svg>
  );
}
