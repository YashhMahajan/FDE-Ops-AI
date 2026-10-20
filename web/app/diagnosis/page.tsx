"use client";

import { useEffect, useState } from "react";
import { useTenant } from "@/components/TenantContext";
import { Chip, IntervalBar, Load, PageHead, verdictTone } from "@/components/ui";
import { useJson } from "@/lib/data";
import { label, pct } from "@/lib/format";
import type { Diagnosis } from "@/lib/types";

export default function DiagnosisPage() {
  const { path } = useTenant();
  const data = useJson<Diagnosis>(path("diagnosis.json"));
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    if (data.state === "ready") setSelected((s) => s ?? data.data.clusters[0]?.cluster.id ?? null);
  }, [data]);
  return (
    <>
      <PageHead
        title="Diagnosis"
        lede="A deterministic classifier gives each failed trial one class. Each intervention runs the cluster again with one change, and also runs control cases that passed. A cause is confirmed only when an intervention fixes the cluster and does not break the control cases."
      />
      <Load value={data}>
        {(d) => {
          const c = d.clusters.find((x) => x.cluster.id === selected) ?? d.clusters[0];
          return (
            <div className="grid-split">
              <div className="panel">
                <div className="panel-head">
                  <span className="placard">Clusters</span>
                  <span className="spacer" />
                  <span className="muted">
                    {d.n_failures} of {d.n_trials} trials failed
                  </span>
                </div>
                <div className="list" role="listbox" aria-label="Clusters">
                  {d.clusters.map((x) => (
                    <button key={x.cluster.id} type="button" role="option" className="list-item" aria-selected={x.cluster.id === c?.cluster.id} onClick={() => setSelected(x.cluster.id)}>
                      <span className="mono">{label(x.cluster.failure_class)}</span>
                      <span className="muted">{label(x.cluster.scenario)}</span>
                      <div className="row">
                        <Chip tone={verdictTone(x.verdict)}>{x.verdict}</Chip>
                        <span className="muted">
                          {x.cluster.n_trials} trials · {pct(x.cluster.share_of_failures, 0)}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
              {c && (
                <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                  <div className="panel">
                    <div className="panel-body" style={{ display: "grid", gap: 10 }}>
                      <div className="row">
                        <Chip tone={verdictTone(c.verdict)}>{c.verdict}</Chip>
                        {c.recommended_fix && <Chip tone="pass">fix: {c.recommended_fix}</Chip>}
                      </div>
                      <p style={{ margin: 0 }}>{c.rationale}</p>
                      <div>
                        <span className="placard">Evidence</span>
                        <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                          {c.cluster.examples.map((e, i) => (
                            <li key={i}>
                              <span className="mono">{e.kind}</span> <span className="mono muted">{e.ref}</span> — {e.detail}
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </div>
                  <div className="panel">
                    <div className="panel-head">
                      <span className="placard">Interventions</span>
                    </div>
                    <table className="table">
                      <thead>
                        <tr>
                          <th>Change</th>
                          <th>Fix rate (95% CI)</th>
                          <th className="num">Fixed</th>
                          <th>Regressions in control cases</th>
                        </tr>
                      </thead>
                      <tbody>
                        {c.results.map((r) => (
                          <tr key={r.intervention_id}>
                            <td>
                              <div className="mono">{r.intervention_id}</div>
                              <div className="muted" style={{ fontSize: 12.5 }}>
                                {r.description} {!r.deployable && <Chip tone="off">diagnostic only</Chip>}
                              </div>
                            </td>
                            <td style={{ minWidth: 160 }}>
                              <IntervalBar value={r.fix_rate} lo={r.fix_ci[0]} hi={r.fix_ci[1]} />
                              <span className="mono muted">
                                {pct(r.fix_rate, 0)} ({pct(r.fix_ci[0], 0)}–{pct(r.fix_ci[1], 0)})
                              </span>
                            </td>
                            <td className="num">
                              {r.fixed}/{r.n_cases}
                            </td>
                            <td className="mono">
                              {r.regressions} of {r.n_control} · max {pct(r.regression_ci[1], 0)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          );
        }}
      </Load>
    </>
  );
}
