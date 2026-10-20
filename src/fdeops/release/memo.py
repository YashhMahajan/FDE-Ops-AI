"""The decision memo: one page that a reviewer reads before an approval. Language: ASD-STE100."""

from fdeops.release.models import ReleaseDecision

STATUS_TEXT = {
    "pending_approval": "All gates passed. The release waits for a person with the approver role.",
    "approved": "A person with the approver role approved the release. It is in production.",
    "rejected": "A person with the approver role rejected the release.",
    "rejected_by_gates": "One or more gates failed. The release cannot get an approval.",
}


def render_memo(d: ReleaseDecision) -> str:
    r = d.release
    lines = [
        f"# Release decision `{d.decision_id}`",
        "",
        f"**Status: {d.status}.** {STATUS_TEXT[d.status]}",
        "",
        f"- Tenant: `{d.tenant_id}`. Release: `{r.version}` (`{r.release_id}`).",
        f"- Agent configuration: `{r.agent_config_id}` (`{r.agent_config_hash[:19]}`).",
        f"- Bundle hash: `{r.bundle_hash[:19]}`. Knowledge base: `{r.kb_hash[:19]}`.",
        f"- Candidate run: `{d.candidate_run_id}`. Baseline run: `{d.baseline_run_id or '-'}`.",
        "",
        "## Gates",
        "",
        "| gate | result | measured | threshold | explanation |",
        "|---|---|---|---|---|",
        *[f"| `{g.gate}` | {g.status} | {g.observed} | {g.threshold} | {g.why} |" for g in d.gates],
        "",
    ]
    if d.notes:
        lines += ["## Evidence", "", d.notes, ""]
    if d.regression_cases:
        lines += [
            f"The approval adds {len(d.regression_cases)} case(s) to the regression suite.",
            "",
        ]
    if d.approval is not None:
        a = d.approval
        lines += [
            "## Approval",
            "",
            f"`{a.approver}` ({a.role}) selected **{a.decision}** at "
            f"{a.at:%Y-%m-%d %H:%M} UTC. Comment: {a.comment or '-'}.",
            "",
        ]
    return "\n".join(lines)
