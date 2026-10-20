"use client";

import { useState } from "react";
import { Annunciator } from "@/components/Annunciator";
import { TicketStrip, ToleranceBar } from "@/components/charts";
import { useTenant } from "@/components/TenantContext";
import { Chip, Load, Markdown, PageHead, Tabs } from "@/components/ui";
import { useJson } from "@/lib/data";
import { label, num, pct } from "@/lib/format";
import type { GateResult, MonitorExport, MonitorReport, MonitorResult } from "@/lib/types";

const WINDOWS = ["during_incident", "after_fix"] as const;
type Window = (typeof WINDOWS)[number];

const LAMP: Record<MonitorResult["status"], GateResult["status"]> = {
  alert: "fail",
  ok: "pass",
  "too few samples": "not_measured",
  "not measured": "not_measured",
};

const MONITOR_STATE: Record<GateResult["status"], string> = {
  pass: "ok",
  fail: "alert",
  not_measured: "no data",
  not_applicable: "n / a",
};

const id = (r: MonitorResult) => (r.direction === "down" ? `${r.signal}_down` : r.signal);

function value(r: MonitorResult, x: number): string {
  return r.statistic === "rate" ? pct(x) : num(x);
}

function lamps(rep: MonitorReport): GateResult[] {
  return rep.results.map((r) => ({
    gate: id(r),
    status: LAMP[r.status],
    passed: r.status !== "alert",
    observed: `${value(r, r.reference)} → ${value(r, r.current)}`,
    threshold: r.statistic === "rate" ? `+${pct(r.tolerance, 0)} pts` : `+${pct(r.tolerance, 0)}`,
    why: r.why,
  }));
}

function Alerts({ rep }: { rep: MonitorReport }) {
  const alerts = rep.results.filter((r) => r.status === "alert");
  if (!alerts.length)
    return (
      <div className="panel">
        <div className="panel-body">
          <Chip tone="pass">no alerts</Chip>{" "}
          <span className="muted">All monitors are in their tolerance. Continue to review a sample of the traffic without a flag.</span>
        </div>
      </div>
    );
  const ordered = [...alerts].sort((a, b) => (a.detected_after ?? 1e9) - (b.detected_after ?? 1e9));
  return (
    <div className="panel">
      <div className="panel-head">
        <span className="placard">Alerts in order of detection</span>
        <span className="spacer" />
        <span className="muted">{rep.quality.trials} tickets in the current window</span>
      </div>
      <ol className="alert-list">
        {ordered.map((r) => (
          <li key={id(r)} className="alert-entry">
            <div className="row">
              <Chip tone={r.severity === "page" ? "fail" : "warn"}>{r.severity}</Chip>
              <span className="alert-signal">{label(id(r))}</span>
              <span className="mono muted">
                {value(r, r.reference)} → {value(r, r.current)}
              </span>
            </div>
            <p className="muted" style={{ margin: "4px 0 8px" }}>
              {r.description} {r.why}
            </p>
            {rep.streams[r.signal] && (
              <TicketStrip flags={rep.streams[r.signal]!} alarmAt={r.detected_after} tone={r.severity === "page" ? "var(--lamp-fail)" : "var(--lamp-warn)"} />
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

function Quality({ rep }: { rep: MonitorReport }) {
  const q = rep.quality;
  return (
    <div className="panel">
      <div className="panel-head">
        <span className="placard">Detection quality · uses the oracle, simulation only</span>
      </div>
      <div className="stats">
        <div className="stat">
          <span className="placard">Failures seen</span>
          <span className="stat-value">
            {q.seen} / {q.failures}
          </span>
          <span className="muted">failed trials with a monitored flag</span>
        </div>
        <div className="stat">
          <span className="placard">Silent failures</span>
          <span className="stat-value">{q.silent}</span>
          <span className="muted">
            {pct(q.silent_rate)} of traffic · max {pct(q.silent_rate_hi)}
          </span>
        </div>
        <div className="stat">
          <span className="placard">Review sample</span>
          <span className="stat-value">{q.review_sample ?? "—"}</span>
          <span className="muted">{q.review_sample ? "tickets for a 95% chance to see one" : "no silent failures in this window"}</span>
        </div>
      </div>
      <table className="table">
        <thead>
          <tr>
            <th>Signal</th>
            <th className="num">Flagged</th>
            <th className="num">Precision</th>
            <th className="num">Recall</th>
          </tr>
        </thead>
        <tbody>
          {q.signals
            .filter((s) => s.flagged)
            .map((s) => (
              <tr key={s.signal}>
                <td className="mono">{label(s.signal)}</td>
                <td className="num">{s.flagged}</td>
                <td className="num">{pct(s.precision, 0)}</td>
                <td className="num">{pct(s.recall, 0)}</td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}

export default function MonitorPage() {
  const { path } = useTenant();
  const data = useJson<MonitorExport>(path("monitor.json"));
  const [win, setWin] = useState<Window>("during_incident");
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <>
      <PageHead
        title="Production monitor"
        lede="Production traffic has no oracle. The monitor uses only signals that a live deployment can see: guardrail flags, superseded knowledge in the context, escalations, tool errors, latency and tokens. An alert occurs only when all of the 95% interval of the change is more than the tolerance."
      />
      <Load value={data}>
        {(d) => {
          const rep = d[win] ?? d.during_incident;
          if (!rep) return <div className="empty">This export has no monitor report.</div>;
          const sel = rep.results.find((r) => id(r) === selected);
          return (
            <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
              <div className="row">
                <Tabs value={win} options={WINDOWS.filter((w) => d[w])} onChange={(w) => setWin(w)} />
                <span className="spacer" />
                <span className="mono muted">
                  reference {rep.reference_run} · current {rep.current_run}
                </span>
              </div>
              <Annunciator gates={lamps(rep)} stateText={MONITOR_STATE} ariaLabel="Production monitors" selected={selected} onSelect={(g) => setSelected((s) => (s === g ? null : g))} />
              {sel && (
                <div className="panel">
                  <div className="panel-body">
                    <span className="placard">{label(id(sel))}</span>
                    <p style={{ margin: "6px 0" }}>
                      {sel.description} {sel.why}
                    </p>
                    <span className="mono muted">
                      status {sel.status} · {value(sel, sel.reference)} → {value(sel, sel.current)} · n = {sel.n_reference} / {sel.n_current}
                    </span>
                  </div>
                </div>
              )}
              <Alerts rep={rep} />
              <div className="panel">
                <div className="panel-head">
                  <span className="placard">All monitors</span>
                  <span className="spacer" />
                  <span className="muted">line = 95% interval · shaded = past the tolerance</span>
                </div>
                <div className="table-scroll">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Signal</th>
                        <th>Status</th>
                        <th className="num">Reference</th>
                        <th className="num">Current</th>
                        <th>Change against tolerance</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rep.results.map((r) => (
                        <tr key={id(r)}>
                          <td>
                            <div className="mono">{label(id(r))}</div>
                            <div className="muted" style={{ fontSize: 12.5 }}>
                              {r.statistic} · {r.severity}
                            </div>
                          </td>
                          <td>
                            <Chip tone={r.status === "alert" ? "fail" : r.status === "ok" ? "pass" : "warn"}>{r.status}</Chip>
                          </td>
                          <td className="num">{value(r, r.reference)}</td>
                          <td className="num">{value(r, r.current)}</td>
                          <td>
                            {r.status === "ok" || r.status === "alert" ? (
                              <ToleranceBar lo={r.lo} hi={r.hi} change={r.change} tolerance={r.tolerance} alert={r.status === "alert"} />
                            ) : (
                              <span className="muted">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <Quality rep={rep} />
              <details className="panel">
                <summary className="panel-head placard">Full monitor report</summary>
                <div className="panel-body">
                  <Markdown source={rep.report_md} />
                </div>
              </details>
            </div>
          );
        }}
      </Load>
    </>
  );
}
