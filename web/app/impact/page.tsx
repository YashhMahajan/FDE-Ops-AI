"use client";

import { PercentileBands } from "@/components/charts";
import { useTenant } from "@/components/TenantContext";
import { Load, Markdown, PageHead } from "@/components/ui";
import { useJson } from "@/lib/data";
import { money, num, pct } from "@/lib/format";
import type { Distribution, Impact } from "@/lib/types";

export default function ImpactPage() {
  const { path } = useTenant();
  const data = useJson<Impact>(path("impact.json"));
  return (
    <>
      <PageHead
        title="Business value"
        lede="Measured outcomes from the run, and assumptions from the tenant cost file with a range for each value. A Monte Carlo simulation gives a distribution, not one number. The FAQ baseline has no LLM: the agent must be better than it."
      />
      <Load value={data}>
        {(d) => {
          const perTicket: [string, Distribution][] = [
            ["Person only", d.human_cost_per_ticket],
            ...(d.baseline_cost_per_ticket ? [["FAQ baseline", d.baseline_cost_per_ticket] as [string, Distribution]] : []),
            ["With the agent", d.agent_cost_per_ticket],
          ];
          const savings: [string, Distribution][] = [
            ["Against a person only", d.monthly_savings_vs_human],
            ...(d.monthly_savings_vs_baseline ? [["Against the FAQ baseline", d.monthly_savings_vs_baseline] as [string, Distribution]] : []),
          ];
          const s = d.monthly_savings_vs_human;
          return (
            <>
              <div className="stats reveal">
                <div className="stat">
                  <span className="placard">Savings each month (median)</span>
                  <span className="stat-value">{money(s.p50)}</span>
                  <span className="stat-note">
                    5th–95th: {money(s.p5)} to {money(s.p95)}
                  </span>
                </div>
                <div className="stat">
                  <span className="placard">Probability above zero</span>
                  <span className="stat-value">{pct(s.prob_positive, 0)}</span>
                  <span className="stat-note">{num(d.draws)} samples</span>
                </div>
                <div className="stat">
                  <span className="placard">Payback (median)</span>
                  <span className="stat-value">{num(d.payback_months.p50, 1)}</span>
                  <span className="stat-note">months for the integration cost</span>
                </div>
                <div className="stat">
                  <span className="placard">Automation (measured)</span>
                  <span className="stat-value">{pct(d.measured.automation_rate, 0)}</span>
                  <span className="stat-note">
                    FAQ baseline: {d.baseline ? pct(d.baseline.automation_rate, 0) : "—"}
                  </span>
                </div>
              </div>
              <div className="grid-2">
                <section className="panel">
                  <div className="panel-head">
                    <span className="placard">Cost for each ticket</span>
                  </div>
                  <div className="panel-body">
                    <PercentileBands rows={perTicket} format={(x) => money(x, 2)} />
                  </div>
                </section>
                <section className="panel">
                  <div className="panel-head">
                    <span className="placard">Savings for each month</span>
                  </div>
                  <div className="panel-body">
                    <PercentileBands rows={savings} />
                  </div>
                </section>
              </div>
              <section className="panel">
                <div className="panel-head">
                  <span className="placard">Full report · measured values and assumptions</span>
                </div>
                <div className="panel-body">
                  <Markdown source={d.report_md} />
                </div>
              </section>
            </>
          );
        }}
      </Load>
    </>
  );
}
