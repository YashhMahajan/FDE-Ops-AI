"use client";

import Link from "next/link";
import { RunRuler } from "@/components/charts";
import { useTenant } from "@/components/TenantContext";
import { Chip, Load, PageHead } from "@/components/ui";
import { useJson } from "@/lib/data";
import { num, pct } from "@/lib/format";
import type { Releases } from "@/lib/types";

const STEP_LINK: Record<string, { href: string; label: string }> = {
  release_v1: { href: "/releases/", label: "Open the gates" },
  incident: { href: "/monitor/", label: "Open the monitor" },
  regression: { href: "/runs/", label: "Open the comparison" },
  diagnosis: { href: "/diagnosis/", label: "Open the diagnosis" },
  release_v2: { href: "/releases/", label: "Open the decision" },
  impact: { href: "/impact/", label: "Open the ROI" },
};

const RUN_NAMES: Record<string, string> = {
  v1_test: "v1 before the incident",
  monitor_test: "v1 under the incident",
  monitor_dev: "v1 under the incident (dev split)",
  v2_test: "v2 with the fix",
  faq_test: "FAQ baseline (no LLM)",
};

const RUN_TONES: Record<string, string> = {
  v1_test: "var(--ink-2)",
  monitor_test: "var(--lamp-fail)",
  v2_test: "var(--lamp-pass)",
  faq_test: "var(--ink-3)",
};

export default function Overview() {
  const { index, path } = useTenant();
  const releases = useJson<Releases>(path("releases.json"));
  return (
    <Load value={index}>
      {(ix) => {
        const ruler = ["v1_test", "monitor_test", "v2_test", "faq_test"]
          .map((k) => ix.runs.find((r) => r.label === k))
          .filter((r): r is NonNullable<typeof r> => Boolean(r))
          .map((r) => ({ name: RUN_NAMES[r.label] ?? r.label, value: r.success, lo: r.ci[0], hi: r.ci[1], tone: RUN_TONES[r.label] ?? "var(--ink)" }));
        const prod = releases.state === "ready" ? releases.data.production : null;
        return (
          <>
            <PageHead
              title={`${ix.tenant.display_name.replace(" (fictional)", "")} release log`}
              lede={ix.tenant.notes}
            />
            <div className="stats reveal">
              <div className="stat">
                <span className="placard">In production</span>
                <span className="stat-value">{prod?.version ?? "—"}</span>
                <span className="stat-note mono">{prod?.release_id ?? "no release"}</span>
              </div>
              <div className="stat">
                <span className="placard">Scenarios</span>
                <span className="stat-value">{ix.tenant.scenarios.length}</span>
                <span className="stat-note">{ix.tenant.pack} pack · {ix.tenant.kb_sections} KB sections</span>
              </div>
              <div className="stat">
                <span className="placard">Data quality</span>
                <span className="stat-value">{num(ix.tenant.data_quality.loaded)}</span>
                <span className="stat-note">records loaded · {ix.tenant.data_quality.isolated} isolated</span>
              </div>
              <div className="stat">
                <span className="placard">PII redaction</span>
                <span className="stat-value">{ix.tenant.pii_redaction ? "On" : "Off"}</span>
                <span className="stat-note">in stored traces</span>
              </div>
            </div>

            <section className="panel">
              <div className="panel-head">
                <span className="placard">Task success on the test split</span>
                <span className="muted" style={{ fontSize: 13 }}>dot = rate · line = 95% confidence interval</span>
              </div>
              <div className="panel-body">
                <RunRuler runs={ruler} />
              </div>
            </section>

            <section>
              <div className="row" style={{ marginBottom: 10 }}>
                <span className="placard">Logbook: incident to approved fix</span>
              </div>
              <ol className="logbook reveal">
                {ix.steps.map((s, i) => (
                  <li className="log-entry" key={s.key}>
                    <span className="log-key">
                      {String(i + 1).padStart(2, "0")} · {s.key.replace("_", " ")}
                    </span>
                    <div>
                      <h2 className="log-title">{s.title}</h2>
                      <p className="log-text">{s.text}</p>
                      <div className="row" style={{ marginTop: 8 }}>
                        {Object.entries(s.refs).map(([k, v]) => (
                          <span key={k} className="mono muted">
                            {k}: {v}
                          </span>
                        ))}
                      </div>
                    </div>
                    {STEP_LINK[s.key] && (
                      <Link className="button" href={STEP_LINK[s.key]!.href}>
                        {STEP_LINK[s.key]!.label}
                      </Link>
                    )}
                  </li>
                ))}
              </ol>
            </section>

            <section className="panel">
              <div className="panel-head">
                <span className="placard">Runs in this export</span>
              </div>
              <table className="table">
                <thead>
                  <tr>
                    <th>Run</th>
                    <th>Configuration</th>
                    <th>Split</th>
                    <th>Incident</th>
                    <th className="num">Success</th>
                    <th className="num">Critical trials</th>
                  </tr>
                </thead>
                <tbody>
                  {ix.runs.map((r) => (
                    <tr key={r.run_id}>
                      <td>
                        <div>{RUN_NAMES[r.label] ?? r.label}</div>
                        <div className="mono muted">{r.run_id}</div>
                      </td>
                      <td className="mono">{r.config}</td>
                      <td>{r.split}</td>
                      <td>{r.incident ? <Chip tone="fail">{r.incident}</Chip> : <span className="muted">—</span>}</td>
                      <td className="num">{pct(r.success)}</td>
                      <td className="num">{r.critical_trials}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </>
        );
      }}
    </Load>
  );
}
