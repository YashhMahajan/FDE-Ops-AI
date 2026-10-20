"use client";

import { useTenant } from "@/components/TenantContext";
import { Chip, Load, Markdown, PageHead, verdictTone } from "@/components/ui";
import { useJson } from "@/lib/data";
import { money, num, pct } from "@/lib/format";
import type { Opportunity } from "@/lib/types";

function Formula({ o }: { o: Opportunity }) {
  return (
    <div className="formula" aria-label="Score formula">
      <span className="term">
        <small>cost / month</small>
        {money(o.cost_per_month)}
      </span>
      ×
      <span className="term">
        <small>fix rate (lower)</small>
        {pct(o.fix_rate_lower, 0)}
      </span>
      ×
      <span className="term">
        <small>confidence</small>
        {pct(o.confidence, 0)}
      </span>
      ÷
      <span className="term">
        <small>effort weeks</small>
        {num(o.effort_weeks, 1)}
      </span>
      =
      <span className="term" style={{ borderColor: "var(--lamp-warn)" }}>
        <small>score</small>
        {num(o.score)}
      </span>
    </div>
  );
}

export default function RoadmapPage() {
  const { path, tenantId } = useTenant();
  const data = useJson<{ opportunities: Opportunity[]; roadmap_md: string }>(path("opportunities.json"));
  return (
    <>
      <PageHead
        title="Roadmap"
        lede="Each failure cluster becomes an opportunity with its evidence, its cost, a validated fix and an effort estimate. The score formula is visible, and a person must check the effort values."
      />
      <Load value={data}>
        {(d) => (
          <>
            <div className="reveal" style={{ display: "grid", gap: 14 }}>
              {d.opportunities.map((o, i) => (
                <article className="panel" key={o.id}>
                  <div className="panel-head">
                    <span className="placard">#{i + 1}</span>
                    <strong>{o.title}</strong>
                    <span className="spacer" />
                    <Chip tone={o.decision === "build" ? "pass" : "off"}>{o.decision}</Chip>
                  </div>
                  <div className="panel-body" style={{ display: "grid", gap: 12 }}>
                    <div className="row">
                      <Chip tone={o.severity === "critical" ? "fail" : "warn"}>{o.severity}</Chip>
                      <Chip tone={verdictTone(o.verdict)}>{o.verdict}</Chip>
                      {o.fix && <span className="mono">fix: {o.fix}</span>}
                      <span className="muted">
                        {pct(o.affected_share)} of trials · about {num(o.affected_tickets_per_month)} tickets each month
                      </span>
                    </div>
                    <Formula o={o} />
                    <p style={{ margin: 0, color: "var(--ink-2)" }}>
                      {o.reason} {o.validation_plan}
                    </p>
                  </div>
                </article>
              ))}
            </div>
            <section className="panel">
              <div className="panel-head">
                <span className="placard">Roadmap memo · {tenantId}</span>
              </div>
              <div className="panel-body">
                <Markdown source={d.roadmap_md} />
              </div>
            </section>
          </>
        )}
      </Load>
    </>
  );
}
