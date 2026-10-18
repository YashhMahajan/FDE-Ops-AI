"""ROI report in Markdown. Language: ASD-STE100. Measured numbers and assumptions are separate."""

import math

from fdeops.eval.report import PROVENANCE_NOTE
from fdeops.impact.roi import Distribution, ROIResult


def _money(x: float) -> str:
    return "not possible" if math.isinf(x) else f"${x:,.2f}"


def _row(name: str, d: Distribution, unit: str = "money") -> str:
    fmt = (
        _money if unit == "money" else (lambda v: "not possible" if math.isinf(v) else f"{v:,.1f}")
    )
    return f"| {name} | {fmt(d.p5)} | {fmt(d.p50)} | {fmt(d.p95)} | {d.prob_positive:.0%} |"


def render_roi(r: ROIResult) -> str:
    m = r.measured
    lines = [
        f"> **Provenance: {m.provenance.value}** (measured part). "
        f"{PROVENANCE_NOTE[m.provenance]} The business values are assumptions.",
        "",
        f"# ROI estimate for `{r.tenant_id}` (run `{r.run_id}`)",
        "",
        "The estimate uses measured outcomes from the run and assumptions from the tenant cost "
        f"file. A Monte Carlo simulation with {r.draws:,} samples gives the uncertainty.",
        "",
        "## Measured in the run",
        "",
        f"- Automation rate (correct, without a person): {m.automation_rate:.1%}.",
        f"- Correct escalation rate: {m.escalation_rate:.1%}.",
        f"- Critical error rate: {m.critical_error_rate:.1%}.",
        f"- Model cost for each ticket: ${m.model_cost_per_ticket:.4f}.",
        "",
        "| category | trials | resolved | escalated | failed | critical |",
        "|---|---:|---:|---:|---:|---:|",
        *[
            f"| `{c.category}` | {c.n_trials} | {c.resolved} | {c.escalated} | {c.failed} | "
            f"{c.failed_critical} |"
            for c in m.categories
        ],
        "",
        "## Results",
        "",
        "| value | 5th percentile | median | 95th percentile | probability above zero |",
        "|---|---:|---:|---:|---:|",
        _row("cost for each ticket, person only", r.human_cost_per_ticket),
        _row("cost for each ticket, with the agent", r.agent_cost_per_ticket),
        *(
            [_row("cost for each ticket, FAQ baseline", r.baseline_cost_per_ticket)]
            if r.baseline_cost_per_ticket
            else []
        ),
        _row("savings for each month against a person only", r.monthly_savings_vs_human),
        *(
            [_row("savings for each month against the FAQ baseline", r.monthly_savings_vs_baseline)]
            if r.monthly_savings_vs_baseline
            else []
        ),
        _row("months to pay back the integration", r.payback_months, unit="number"),
        _row("cost for each automated resolution", r.cost_per_automated_resolution),
        "",
        "## Assumptions",
        "",
        "These values are assumptions, not measurements. Change them in the tenant cost file.",
        "",
        "| assumption | low | likely | high | source |",
        "|---|---:|---:|---:|---|",
    ]
    a = r.assumptions
    singles = {
        "staff_cost_per_hour": a.staff_cost_per_hour,
        "monthly_ticket_volume": a.monthly_ticket_volume,
        "adoption_rate": a.adoption_rate,
        "rework_minutes": a.rework_minutes,
        "triage_saving_minutes": a.triage_saving_minutes,
        "critical_error_cost": a.critical_error_cost,
        "infrastructure_per_month": a.infrastructure_per_month,
        "maintenance_per_month": a.maintenance_per_month,
        "integration_one_time": a.integration_one_time,
    }
    singles.update({f"handling_minutes.{k}": v for k, v in a.handling_minutes.items()})
    lines += [
        f"| `{k}` | {v.low:,.2f} | {v.likely:,.2f} | {v.high:,.2f} | {v.source} |"
        for k, v in singles.items()
    ]
    lines += [
        "",
        "The traffic mix of the categories is the mix of the dataset. This is also an assumption.",
        "",
    ]
    return "\n".join(lines)
