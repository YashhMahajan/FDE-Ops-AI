"use client";

import { useState } from "react";
import { ForestPlot } from "@/components/charts";
import { useTenant } from "@/components/TenantContext";
import { Chip, Load, PageHead } from "@/components/ui";
import { useJson } from "@/lib/data";
import { pct, signed } from "@/lib/format";
import type { Comparison } from "@/lib/types";

const NAMES: Record<string, string> = {
  v1_vs_monitor: "v1 before and under the incident",
  monitor_vs_v2: "v1 under the incident and v2 with the fix",
};

function verdict(c: Comparison): { text: string; tone: "pass" | "fail" | "off" } {
  if (c.diff.hi < 0 && c.mcnemar_p < 0.05) return { text: "regression", tone: "fail" };
  if (c.diff.lo > 0 && c.mcnemar_p < 0.05) return { text: "improvement", tone: "pass" };
  return { text: "no credible difference", tone: "off" };
}

export default function RunsPage() {
  const { index, path } = useTenant();
  const [name, setName] = useState("v1_vs_monitor");
  const [by, setBy] = useState<"scenario" | "tag">("scenario");
  const cmp = useJson<Comparison>(path(`compare/${name}.json`));
  return (
    <>
      <PageHead
        title="Comparisons"
        lede="Paired comparisons at case level. Each row is the change from A to B with a 95% confidence interval. A row that does not cross the zero line is a credible change. Holm-adjusted p-values control the error across many rows."
      />
      <Load value={index}>
        {(ix) => (
          <div className="segmented" role="group" aria-label="Comparison">
            {ix.comparisons.map((c) => (
              <button key={c} type="button" aria-pressed={c === name} onClick={() => setName(c)}>
                {NAMES[c] ?? c}
              </button>
            ))}
          </div>
        )}
      </Load>
      <Load value={cmp}>
        {(c) => {
          const v = verdict(c);
          const rows = Object.entries(by === "scenario" ? c.by_scenario : c.by_tag).sort((a, b) => a[1].mean - b[1].mean);
          return (
            <>
              <div className="stats reveal">
                <div className="stat">
                  <span className="placard">Verdict</span>
                  <span className="stat-value" style={{ fontSize: 24 }}>
                    <Chip tone={v.tone}>{v.text}</Chip>
                  </span>
                  <span className="stat-note">exact sign test p = {c.mcnemar_p.toFixed(4)}</span>
                </div>
                <div className="stat">
                  <span className="placard">Success A → B</span>
                  <span className="stat-value">
                    {pct(c.a_rate, 0)} → {pct(c.b_rate, 0)}
                  </span>
                  <span className="stat-note">{c.n_pairs} paired cases × {c.trials} trial(s)</span>
                </div>
                <div className="stat">
                  <span className="placard">Difference</span>
                  <span className="stat-value">{signed(c.diff.mean, 3)}</span>
                  <span className="stat-note">
                    95% CI {signed(c.diff.lo, 3)} to {signed(c.diff.hi, 3)}
                  </span>
                </div>
                <div className="stat">
                  <span className="placard">Cases that changed</span>
                  <span className="stat-value">
                    {c.b_only} / {c.a_only}
                  </span>
                  <span className="stat-note">better in B / better in A</span>
                </div>
              </div>
              <section className="panel">
                <div className="panel-head">
                  <span className="placard">
                    {c.b_config} (B) against {c.a_config} (A)
                  </span>
                  <span className="spacer" />
                  <div className="segmented" role="group" aria-label="Slices">
                    {(["scenario", "tag"] as const).map((b) => (
                      <button key={b} type="button" aria-pressed={by === b} onClick={() => setBy(b)}>
                        by {b}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="panel-body">
                  <ForestPlot rows={rows} pvals={by === "scenario" ? c.holm_p : c.tag_holm_p} />
                </div>
              </section>
            </>
          );
        }}
      </Load>
    </>
  );
}
