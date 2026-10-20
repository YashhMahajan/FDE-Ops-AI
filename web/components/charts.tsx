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
  const lim = Math.max(0.25, ...rows.flatMap(([, d]) => [Math.abs(d.lo), Math.abs(d.hi)])) * 1.1;
  const x = (v: number) => left + ((v + lim) / (2 * lim)) * (width - left - right);
  const height = rows.length * rowH + 40;
  const ticks = [-lim, -lim / 2, 0, lim / 2, lim].map((t) => Math.round(t * 100) / 100);
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
