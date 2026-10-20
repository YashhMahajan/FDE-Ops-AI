"use client";

import { useEffect, useMemo, useState } from "react";
import { useTenant } from "@/components/TenantContext";
import { Chip, Drawer, Load, PageHead, Tabs } from "@/components/ui";
import { useJson } from "@/lib/data";
import { label, num, short } from "@/lib/format";
import type { RunFile, TrialDetail } from "@/lib/types";

const TABS = ["transcript", "tool_calls", "spans", "scores"] as const;
type Tab = (typeof TABS)[number];

function Detail({ runId, caseId, trial }: { runId: string; caseId: string; trial: number }) {
  const { path } = useTenant();
  const detail = useJson<TrialDetail>(path(`trials/${runId}/${caseId}-${trial}.json`));
  const [tab, setTab] = useState<Tab>("transcript");
  return (
    <Load value={detail}>
      {(t) => {
        const spans = t.episode.trace.spans.filter((s) => ["llm", "tool", "retrieval"].includes(s.kind));
        const latency = (s: (typeof spans)[number]) => Number(s.attributes["fdeops.latency_ms"] ?? 0);
        const total = spans.reduce((a, s) => a + latency(s), 0) || 1;
        let cursor = 0;
        return (
          <>
            <div className="drawer-head">
              <div className="row">
                <Chip tone={t.success ? "pass" : "fail"}>{t.success ? "correct" : "failed"}</Chip>
                <strong className="placard" style={{ fontSize: 16, color: "var(--ink)" }}>
                  {label(t.scenario)}
                </strong>
                <span className="mono muted">
                  {t.case_id} · trial {t.trial}
                </span>
              </div>
              <div className="row">
                {t.tags.map((x) => (
                  <span key={x} className="mono muted">
                    #{x}
                  </span>
                ))}
                {t.episode.violations.map((v) => (
                  <Chip key={v.rule} tone="fail">
                    {v.rule}
                  </Chip>
                ))}
                {t.episode.faults_injected.map(([op, k], i) => (
                  <Chip key={i} tone="warn">
                    fault {k} on {op}
                  </Chip>
                ))}
              </div>
              <Tabs value={tab} options={TABS} onChange={setTab} />
            </div>
            <div className="drawer-body">
              {tab === "transcript" &&
                t.episode.transcript
                  .filter((m) => m.role !== "system")
                  .map((m, i) => (
                    <div className="bubble" data-role={m.role} key={i}>
                      <span className="placard">{m.role === "tool" ? `tool · ${m.name}` : m.role}</span>
                      {m.content && <pre>{m.role === "tool" ? readable(m.content) : m.content}</pre>}
                      {m.tool_calls.map((c) => (
                        <pre key={c.id}>
                          → {c.name}({JSON.stringify(c.arguments)})
                        </pre>
                      ))}
                    </div>
                  ))}
              {tab === "tool_calls" && (
                <table className="table">
                  <thead>
                    <tr>
                      <th>Operation</th>
                      <th>Result</th>
                      <th className="num">Tries</th>
                      <th className="num">ms</th>
                    </tr>
                  </thead>
                  <tbody>
                    {t.episode.tool_calls.map((c, i) => (
                      <tr key={i}>
                        <td>
                          <div className="mono">{c.op}</div>
                          <div className="mono muted" style={{ maxWidth: 380, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {JSON.stringify(c.args)}
                          </div>
                        </td>
                        <td>{c.ok ? <Chip tone="pass">ok</Chip> : <Chip tone="fail">{c.error_code}</Chip>}</td>
                        <td className="num">{c.attempts}</td>
                        <td className="num">{num(c.latency_ms, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {tab === "spans" && (
                <div>
                  <p className="muted" style={{ marginTop: 0 }}>
                    Recorded latency of each step. The replay keeps the latency of the original call.
                  </p>
                  {spans.map((s) => {
                    const start = cursor;
                    cursor += latency(s);
                    return (
                      <div className="waterfall-row" key={s.span_id}>
                        <span className="mono" title={s.error ?? undefined}>
                          {s.kind} · {s.name}
                        </span>
                        <div style={{ position: "relative", height: 10 }}>
                          <div
                            className="waterfall-bar"
                            data-kind={s.kind}
                            data-status={s.status}
                            style={{ position: "absolute", left: `${(start / total) * 100}%`, width: `${Math.max(0.6, (latency(s) / total) * 100)}%` }}
                          />
                        </div>
                        <span className="mono muted" style={{ textAlign: "right" }}>
                          {num(latency(s), 0)} ms
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
              {tab === "scores" && (
                <table className="table">
                  <tbody>
                    {t.scores.map((s) => (
                      <tr key={s.name}>
                        <td className="mono">{s.name}</td>
                        <td>
                          {s.passed === null ? (
                            <Chip tone="off">info</Chip>
                          ) : s.passed ? (
                            <Chip tone="pass">pass</Chip>
                          ) : (
                            <Chip tone="fail">{s.critical ? "critical" : "fail"}</Chip>
                          )}
                        </td>
                        <td className="num">{s.value === null ? "—" : num(s.value, 3)}</td>
                        <td className="mono muted" style={{ maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {Object.keys(s.details).length ? JSON.stringify(s.details) : ""}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        );
      }}
    </Load>
  );
}

/** Tool output is JSON. Indent it, and show the line breaks inside its strings as line breaks. */
function readable(content: string): string {
  try {
    return JSON.stringify(JSON.parse(content), null, 2).replace(/\\n/g, "\n");
  } catch {
    return content;
  }
}

export default function TracesPage() {
  const { index, path } = useTenant();
  const [runId, setRunId] = useState<string | null>(null);
  const [filter, setFilter] = useState<"failed" | "all">("failed");
  const [open, setOpen] = useState<{ caseId: string; trial: number } | null>(null);

  useEffect(() => {
    if (index.state === "ready") {
      const ids = index.data.detail_runs;
      if (!runId || !ids.includes(runId)) setRunId(index.data.runs.find((r) => r.label === "monitor_test")?.run_id ?? ids[0] ?? null);
    }
  }, [index, runId]);

  const run = useJson<RunFile>(runId ? path(`runs/${runId}.json`) : null);
  const trials = useMemo(
    () => (run.state === "ready" ? run.data.trials.filter((t) => filter === "all" || !t.success) : []),
    [run, filter],
  );

  return (
    <>
      <PageHead
        title="Traces"
        lede="Each trial of a run, with the ticket, the knowledge that the agent saw, each tool call and each score. Open a trial to see what occurred."
      />
      <Load value={index}>
        {(ix) => (
          <div className="row">
            <select className="select" value={runId ?? ""} onChange={(e) => setRunId(e.target.value)} aria-label="Run">
              {ix.runs
                .filter((r) => ix.detail_runs.includes(r.run_id))
                .map((r) => (
                  <option key={r.run_id} value={r.run_id}>
                    {r.label.replace("_", " ")} · {r.config} · {r.split}
                  </option>
                ))}
            </select>
            <div className="segmented" role="group" aria-label="Filter">
              {(["failed", "all"] as const).map((f) => (
                <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}>
                  {f === "failed" ? "Failed only" : "All trials"}
                </button>
              ))}
            </div>
            <span className="muted">{trials.length} trial(s)</span>
          </div>
        )}
      </Load>
      <section className="panel">
        <Load value={run}>
          {() =>
            trials.length === 0 ? (
              <div className="empty">No failed trials in this run. Select “All trials” to see each trial.</div>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Scenario</th>
                    <th>Case</th>
                    <th>Result</th>
                    <th>Failure class</th>
                    <th>Violations</th>
                    <th className="num">Steps</th>
                  </tr>
                </thead>
                <tbody>
                  {trials.map((t) => (
                    <tr
                      key={`${t.case_id}-${t.trial}`}
                      className="row-button"
                      tabIndex={0}
                      aria-selected={open?.caseId === t.case_id && open.trial === t.trial}
                      onClick={() => setOpen({ caseId: t.case_id, trial: t.trial })}
                      onKeyDown={(e) => e.key === "Enter" && setOpen({ caseId: t.case_id, trial: t.trial })}
                    >
                      <td>{label(t.scenario)}</td>
                      <td className="mono">{short(t.case_id, 14)}</td>
                      <td>{t.success ? <Chip tone="pass">correct</Chip> : <Chip tone="fail">failed</Chip>}</td>
                      <td className="mono">{t.primary_failure ?? "—"}</td>
                      <td className="mono muted">{t.violations.join(", ") || "—"}</td>
                      <td className="num">{t.steps}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          }
        </Load>
      </section>
      <Drawer open={open !== null} onClose={() => setOpen(null)}>
        {open && runId && <Detail runId={runId} caseId={open.caseId} trial={open.trial} />}
      </Drawer>
    </>
  );
}
