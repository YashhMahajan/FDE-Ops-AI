"""The roadmap memo. It also tells what we do not build, and why."""

from fdeops.insights.opportunities import FORMULA, Opportunity


def _money(x: float) -> str:
    return f"${x:,.0f}"


def render_roadmap(opps: list[Opportunity], tenant_id: str, top: int = 3) -> str:
    build = [o for o in opps if o.decision == "build"][:top]
    skip = [o for o in opps if o.decision == "not build"]
    lines = [
        f"# Roadmap memo: `{tenant_id}`",
        "",
        "The values are estimates. They use measured failure rates and the likely value of each "
        "assumption. The effort values come from a person.",
        "",
        "## What we build next",
        "",
    ]
    if not build:
        lines += ["No opportunity has a validated fix at this time.", ""]
    for i, o in enumerate(build, start=1):
        lines += [
            f"### {i}. {o.title}",
            "",
            f"- Problem: {o.problem} It occurs in {o.affected_share:.1%} of trials, about "
            f"{o.affected_tickets_per_month:,.0f} tickets each month.",
            f"- Severity: {o.severity}. Cost of the problem: about {_money(o.cost_per_month)} "
            "each month.",
            f"- Fix: `{o.fix}`. The fix rate is {o.fix_rate_lower:.0%} or more. Verdict: "
            f"{o.verdict}.",
            f"- Expected benefit: about {_money(o.expected_benefit_per_month)} each month for "
            f"{o.effort_weeks:g} engineer weeks ({o.effort_basis}).",
            f"- Score: {o.score:,.0f}. Confidence: {o.confidence:.0%}.",
            f"- Validation plan: {o.validation_plan}",
            f"- Evidence: {'; '.join(o.evidence).replace(';', ',')}.",
            "",
        ]
    fixes = [o.fix for o in build if o.fix]
    if len(set(fixes)) < len(fixes):
        lines += [
            "Two items use the same fix. Do that fix one time, then measure the two items again.",
            "",
        ]
    lines += ["## What we do not build", ""]
    if not skip:
        lines += ["Each opportunity has a validated fix.", ""]
    lines += [
        f"- {o.title}: {o.reason} (cost about {_money(o.cost_per_month)} each month)" for o in skip
    ]
    lines += [
        "",
        "## Rank formula",
        "",
        f"`{FORMULA}`",
        "",
        "The formula prefers fixes that the evidence confirms and that need less effort. A "
        "person must examine the effort values, because they are estimates.",
        "",
    ]
    return "\n".join(lines)
