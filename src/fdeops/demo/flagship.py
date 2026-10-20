"""The flagship demo, from incident to approved fix, in one function.

1. Release v1 (the clean configuration) after its gates pass.
2. Incident: the refund policy changes, and the index keeps the previous section.
3. Monitoring runs of v1 under the incident show a regression (a paired comparison).
4. Diagnosis on the dev split confirms stale knowledge by intervention.
5. The improvement loop proposes v2 and stops. A person with the approver role approves v2.
6. ROI against a person only and against the FAQ baseline, opportunities and a roadmap memo.

Each step keeps its evidence: run IDs, gate results, the decision memo and the reports. With the
heuristic model, each output has the label ``pipeline-test``. With a real model and cassettes, the
same function measures a real agent.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fdeops.agent.config import AgentConfig, ModelRef
from fdeops.core.model import FrozenModel
from fdeops.diagnose.interventions import Diagnosis, diagnose_run
from fdeops.diagnose.report import save_diagnosis
from fdeops.eval.compare import Comparison, compare_runs, render_comparison
from fdeops.eval.incidents import IncidentSpec, load_incident
from fdeops.eval.report import save_run
from fdeops.eval.runner import RunResult, run_eval
from fdeops.impact.baseline import faq_agent
from fdeops.impact.costs import load_costs
from fdeops.impact.measure import measure_run
from fdeops.impact.report import render_roi
from fdeops.impact.roi import ROIResult, simulate_roi
from fdeops.improve.loop import ImprovementResult, improve
from fdeops.insights.opportunities import Opportunity, build_opportunities, load_effort
from fdeops.insights.roadmap import render_roadmap
from fdeops.llm.types import LLMClient
from fdeops.release.gates import evaluate_gates
from fdeops.release.integration import run_integration_suite
from fdeops.release.memo import render_memo
from fdeops.release.models import Release, load_gates
from fdeops.release.registry import ReleaseRegistry
from fdeops.tenancy.loader import Tenant

APPROVER = "demo-approver"


class DemoStep(FrozenModel):
    key: str
    title: str
    text: str
    refs: dict[str, str] = {}


@dataclass
class DemoResult:
    tenant: Tenant
    steps: list[DemoStep] = field(default_factory=list)
    runs: dict[str, RunResult] = field(default_factory=dict)
    comparisons: dict[str, Comparison] = field(default_factory=dict)
    diagnosis: Diagnosis | None = None
    improvement: ImprovementResult | None = None
    roi: ROIResult | None = None
    opportunities: list[Opportunity] = field(default_factory=list)
    registry: ReleaseRegistry | None = None
    reports: dict[str, str] = field(default_factory=dict)


def run_flagship(
    tenant: Tenant,
    config: AgentConfig,
    llm: LLMClient,
    incident: IncidentSpec,
    out: Path,
    dataset_name: str = "support-core",
) -> DemoResult:
    out.mkdir(parents=True, exist_ok=True)
    runs_dir = out / "runs"
    res = DemoResult(tenant=tenant)
    gates = load_gates(tenant.root / "gates.yaml")
    registry = ReleaseRegistry(out / "releases", tenant.id)
    res.registry = registry
    splits = tenant.build_datasets(dataset_name)
    dev, test = splits["dev"], splits["test"]

    def keep(label: str, run: RunResult) -> RunResult:
        save_run(run, runs_dir)
        res.runs[label] = run
        return run

    # 1. v1 goes to production through its gates.
    v1_test = keep("v1_test", run_eval(tenant, config, test, llm))
    integration = run_integration_suite(tenant, config, dev, llm, sample=16)
    results = evaluate_gates(
        tenant,
        gates,
        v1_test,
        baseline=None,
        integration_passed=integration.passed,
        regression_passed=True,
    )
    d1 = registry.propose(
        Release.from_run(tenant, gates, v1_test, "v1"),
        v1_test.run_id,
        None,
        results,
        notes="The first release of the support agent.",
    )
    if d1.status == "pending_approval":
        registry.approve(d1.decision_id, APPROVER, "approver", "gates passed", gates.approver_roles)
    res.steps.append(
        DemoStep(
            key="release_v1",
            title="v1 goes to production",
            text=f"v1 passed {sum(g.passed for g in results)} of {len(results)} gates. Status: "
            f"{registry.decision(d1.decision_id).status}.",
            refs={"run": v1_test.run_id, "decision": d1.decision_id},
        )
    )

    # 2 and 3. The incident, and monitoring that finds the regression.
    mon_test = keep("monitor_test", run_eval(tenant, config, test, llm, incident=incident))
    mon_dev = keep("monitor_dev", run_eval(tenant, config, dev, llm, incident=incident))
    cmp = compare_runs(v1_test, mon_test)
    res.comparisons["v1_vs_monitor"] = cmp
    res.reports["comparison_incident"] = render_comparison(cmp)
    worst = min(cmp.by_scenario.items(), key=lambda kv: kv[1].mean)
    res.steps.append(
        DemoStep(
            key="incident",
            title=f"Incident: {incident.id}",
            text=f"{incident.description} Monitoring of v1 under the incident: success changed by "
            f"{cmp.diff.mean:+.3f} (95% CI {cmp.diff.lo:+.3f} to {cmp.diff.hi:+.3f}). The "
            f"largest change is in {worst[0]} ({worst[1].mean:+.3f}).",
            refs={"baseline_run": v1_test.run_id, "monitor_run": mon_test.run_id},
        )
    )

    # 4. Diagnosis on the dev split.
    diagnosis = diagnose_run(tenant, mon_dev, dev, llm)
    save_diagnosis(diagnosis, runs_dir / mon_dev.run_id)
    res.diagnosis = diagnosis
    top = diagnosis.clusters[0] if diagnosis.clusters else None
    res.steps.append(
        DemoStep(
            key="diagnosis",
            title="Diagnosis",
            text=(
                f"The largest cluster is {top.cluster.id} ({top.cluster.n_trials} trials). "
                f"Verdict: {top.verdict.value}. {top.rationale}"
            )
            if top
            else "No failures to diagnose.",
            refs={"run": mon_dev.run_id},
        )
    )

    # 5. The improvement loop proposes v2. A person approves it.
    result = improve(
        tenant, gates, registry, mon_dev, dev, test, mon_test, llm, version="v2", runs_dir=runs_dir
    )
    res.improvement = result
    approved = None
    if result.status == "pending_approval" and result.decision_id:
        approved = registry.approve(
            result.decision_id,
            APPROVER,
            "approver",
            "The diagnosis and the gates support the fix.",
            gates.approver_roles,
        )
        res.reports["memo_v2"] = render_memo(approved)
    if result.gate_run_id:
        from fdeops.eval.report import load_run

        res.runs["v2_test"] = load_run(runs_dir / result.gate_run_id)
        cmp2 = compare_runs(mon_test, res.runs["v2_test"])
        res.comparisons["monitor_vs_v2"] = cmp2
        res.reports["comparison_fix"] = render_comparison(cmp2)
    res.steps.append(
        DemoStep(
            key="release_v2",
            title="v2 with the fix",
            text=f"Fix: {result.intervention_id}. The loop stopped at {result.status}"
            + (". Then a person with the approver role approved it." if approved else ".")
            + (
                f" Dev change: {result.dev_experiment['diff_mean']:+.3f}."
                if result.dev_experiment
                else ""
            ),
            refs={
                k: v
                for k, v in {"decision": result.decision_id, "run": result.gate_run_id}.items()
                if v
            },
        )
    )

    # 6. Business value and the roadmap.
    costs = load_costs(tenant.root / "costs.yaml")
    faq_config = AgentConfig(id="faq-baseline", model=ModelRef(provider="external", name="faq"))
    faq = keep("faq_test", run_eval(tenant, faq_config, test, None, external_agent=faq_agent))
    final = res.runs.get("v2_test", v1_test)
    res.roi = simulate_roi(
        measure_run(final, costs, gates.pricing),
        costs,
        draws=10_000,
        baseline=measure_run(faq, costs, gates.pricing),
    )
    res.reports["impact"] = render_roi(res.roi)
    res.opportunities = build_opportunities(
        mon_dev,
        diagnosis,
        measure_run(mon_dev, costs, gates.pricing),
        costs,
        load_effort(tenant.root / "effort.yaml"),
    )
    res.reports["roadmap"] = render_roadmap(res.opportunities, tenant.id)
    s = res.roi.monthly_savings_vs_human
    res.steps.append(
        DemoStep(
            key="impact",
            title="Business value",
            text=f"Savings for each month against a person only: median ${s.p50:,.0f} (5th to 95th "
            f"percentile ${s.p5:,.0f} to ${s.p95:,.0f}). These values use assumptions.",
            refs={"run": final.run_id, "baseline_run": faq.run_id},
        )
    )
    for name, text in res.reports.items():
        (out / f"{name}.md").write_text(text, encoding="utf-8")
    return res


def load_flagship_incident(root: Path, tenant_id: str) -> IncidentSpec:
    names = {"ledgerloop": "refund-window-drift", "parcelpoint": "claims-limit-drift"}
    return load_incident(root / "incidents" / tenant_id / f"{names[tenant_id]}.yaml")


def summary(res: DemoResult) -> dict[str, Any]:
    return {
        "tenant": res.tenant.id,
        "steps": [s.model_dump() for s in res.steps],
        "runs": {k: v.run_id for k, v in res.runs.items()},
    }
