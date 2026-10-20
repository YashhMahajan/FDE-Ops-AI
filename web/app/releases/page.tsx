"use client";

import { useEffect, useState } from "react";
import { Annunciator } from "@/components/Annunciator";
import { useTenant } from "@/components/TenantContext";
import { Chip, Load, Markdown, PageHead, statusTone } from "@/components/ui";
import { useJson } from "@/lib/data";
import { label } from "@/lib/format";
import type { Releases } from "@/lib/types";

export default function ReleasesPage() {
  const { path } = useTenant();
  const data = useJson<Releases>(path("releases.json"));
  const [selected, setSelected] = useState<string | null>(null);
  const [gate, setGate] = useState<string | null>(null);

  useEffect(() => {
    if (data.state === "ready" && !selected) {
      const decisions = data.data.decisions;
      setSelected(decisions[decisions.length - 1]?.decision_id ?? null);
    }
  }, [data, selected]);

  return (
    <>
      <PageHead
        title="Release gates"
        lede="A candidate goes to production only when its gates pass and a person with the approver role approves it. Each gate uses a confidence limit, and each gate explains why it exists."
      />
      <Load value={data}>
        {(rel) => {
          const d = rel.decisions.find((x) => x.decision_id === selected) ?? rel.decisions[0];
          const g = d?.gates.find((x) => x.gate === gate) ?? null;
          return (
            <div className="grid-split">
              <div className="panel">
                <div className="panel-head">
                  <span className="placard">Decisions</span>
                  <span className="spacer" />
                  <span className="muted">production: {rel.production?.version ?? "none"}</span>
                </div>
                <div className="list" role="listbox" aria-label="Release decisions">
                  {[...rel.decisions].reverse().map((x) => (
                    <button
                      key={x.decision_id}
                      type="button"
                      role="option"
                      className="list-item"
                      aria-selected={x.decision_id === d?.decision_id}
                      onClick={() => {
                        setSelected(x.decision_id);
                        setGate(null);
                      }}
                    >
                      <div className="row">
                        <strong className="placard" style={{ fontSize: 16, color: "var(--ink)" }}>
                          {x.release.version}
                        </strong>
                        <Chip tone={statusTone(x.status)}>{label(x.status)}</Chip>
                      </div>
                      <span className="mono muted">{x.release.agent_config_id}</span>
                      <span className="muted" style={{ fontSize: 12.5 }}>
                        {x.gates.filter((y) => y.passed).length} of {x.gates.length} gates pass
                      </span>
                    </button>
                  ))}
                </div>
              </div>
              {d && (
                <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
                  <Annunciator gates={d.gates} selected={gate} onSelect={(x) => setGate(gate === x ? null : x)} />
                  <div className="panel">
                    <div className="panel-body">
                      {g ? (
                        <div style={{ display: "grid", gap: 6 }}>
                          <span className="placard">{label(g.gate)}</span>
                          <div>
                            <strong>Measured:</strong> <span className="mono">{g.observed}</span>
                          </div>
                          <div>
                            <strong>Threshold:</strong> <span className="mono">{g.threshold}</span>
                          </div>
                          <p style={{ margin: 0, color: "var(--ink-2)" }}>{g.why}</p>
                        </div>
                      ) : (
                        <span className="muted">Select a lamp to see the measured value, the threshold and the reason for the gate.</span>
                      )}
                    </div>
                  </div>
                  {d.approval && (
                    <div className="panel">
                      <div className="panel-body row">
                        <Chip tone={d.approval.decision === "approve" ? "pass" : "fail"}>{d.approval.decision}</Chip>
                        <span>
                          <strong>{d.approval.approver}</strong> ({d.approval.role}) · {new Date(d.approval.at).toLocaleString()}
                        </span>
                        <span className="muted">“{d.approval.comment}”</span>
                      </div>
                    </div>
                  )}
                  <div className="panel">
                    <div className="panel-head">
                      <span className="placard">Decision memo</span>
                    </div>
                    <div className="panel-body">
                      <Markdown source={d.memo_md} />
                    </div>
                  </div>
                  <div className="panel">
                    <div className="panel-head">
                      <span className="placard">History</span>
                    </div>
                    <table className="table">
                      <tbody>
                        {rel.history.map((h, i) => (
                          <tr key={i}>
                            <td className="mono">{new Date(h.at).toLocaleString()}</td>
                            <td>{h.action}</td>
                            <td>{h.version}</td>
                            <td>
                              {h.actor} <span className="muted">({h.role})</span>
                            </td>
                            <td className="muted">{h.detail}</td>
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
