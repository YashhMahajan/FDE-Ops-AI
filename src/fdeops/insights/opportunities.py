"""Opportunities: one for each failure cluster, with its evidence, cost, fix, effort and score.

score = expected_benefit_per_month * confidence / effort_weeks

- expected_benefit_per_month = cost_per_month * fix_rate_lower_limit (the best deployable fix)
- cost_per_month = monthly volume * adoption * share of trials in the cluster * cost of a failure
- confidence comes from the diagnosis verdict
- effort_weeks comes from the tenant effort file (a person gives it)

All values use the likely value of each assumption. The ROI report has the full uncertainty.
"""

from pathlib import Path
from typing import Literal

from pydantic import field_validator

from fdeops.core.config import load_model
from fdeops.core.model import FrozenModel
from fdeops.diagnose.interventions import Diagnosis, Verdict
from fdeops.diagnose.taxonomy import DESCRIPTIONS, FailureClass
from fdeops.eval.runner import RunResult
from fdeops.impact.costs import CostModel, category_of
from fdeops.impact.measure import RunMeasure

CONFIDENCE = {Verdict.CONFIRMED: 0.9, Verdict.SUPPORTED: 0.5, Verdict.INCONCLUSIVE: 0.2}
CRITICAL_CLASSES = {
    FailureClass.INJECTION_FOLLOWED,
    FailureClass.STALE_KNOWLEDGE,
    FailureClass.PERMISSION_VIOLATION,
    FailureClass.POLICY_VIOLATION,
    FailureClass.MISSED_ESCALATION,
}
FORMULA = (
    "score = expected_benefit_per_month * confidence / effort_weeks; "
    "expected_benefit_per_month = cost_per_month * fix_rate_lower_limit"
)


class EffortItem(FrozenModel):
    weeks: float
    why: str

    @field_validator("weeks")
    @classmethod
    def _positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("an effort estimate must be more than zero weeks")
        return v


class EffortModel(FrozenModel):
    interventions: dict[str, EffortItem]
    default_weeks: float

    @field_validator("default_weeks")
    @classmethod
    def _positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("default_weeks must be more than zero")
        return v


def load_effort(path: Path) -> EffortModel:
    return load_model(path, EffortModel)


class Opportunity(FrozenModel):
    id: str
    title: str
    problem: str
    cluster_id: str
    failure_class: str
    scenario: str
    verdict: str
    evidence: tuple[str, ...]
    affected_share: float
    affected_tickets_per_month: float
    severity: Literal["critical", "major"]
    cost_per_month: float
    fix: str | None
    fix_rate_lower: float
    effort_weeks: float
    effort_basis: str
    confidence: float
    expected_benefit_per_month: float
    score: float
    formula: str
    validation_plan: str
    decision: Literal["build", "not build"]
    reason: str


def build_opportunities(
    run: RunResult, diagnosis: Diagnosis, measure: RunMeasure, costs: CostModel, effort: EffortModel
) -> list[Opportunity]:
    volume = costs.monthly_ticket_volume.likely * costs.adoption_rate.likely
    per_min = costs.staff_cost_per_hour.likely / 60
    out: list[Opportunity] = []
    for cd in diagnosis.clusters:
        c = cd.cluster
        tags = next((r.tags for r in run.results if r.scenario == c.scenario), ())
        minutes = costs.handling_minutes.get(
            category_of(tags, costs), costs.handling_minutes["default"]
        ).likely
        severity: Literal["critical", "major"] = (
            "critical" if c.failure_class in CRITICAL_CLASSES else "major"
        )
        failure_cost = (minutes + costs.rework_minutes.likely) * per_min + (
            costs.critical_error_cost.likely if severity == "critical" else 0.0
        )
        share = c.n_trials / max(len(run.results), 1)
        cost_month = volume * share * failure_cost
        deployable = [r for r in cd.results if r.deployable]
        best = max(deployable, key=lambda r: r.fix_ci[0], default=None)
        fix = cd.recommended_fix or (best.intervention_id if best else None)
        fix_lo = next((r.fix_ci[0] for r in cd.results if r.intervention_id == fix), 0.0)
        item = effort.interventions.get(fix) if fix else None
        weeks = item.weeks if item else effort.default_weeks
        confidence = CONFIDENCE[cd.verdict]
        benefit = cost_month * fix_lo
        score = benefit * confidence / weeks
        if cd.verdict == Verdict.INCONCLUSIVE:
            decision, reason = "not build", "The evidence is not sufficient. Collect more cases."
        elif fix is None or benefit <= 0:
            decision, reason = "not build", "No deployable fix passed the intervention test."
        else:
            decision, reason = (
                "build",
                (f"{fix} fixed {fix_lo:.0%} or more of the cluster in the intervention test."),
            )
        out.append(
            Opportunity(
                id=f"opp:{c.id}",
                title=f"{DESCRIPTIONS[c.failure_class]} ({c.scenario})",
                problem=DESCRIPTIONS[c.failure_class],
                cluster_id=c.id,
                failure_class=c.failure_class.value,
                scenario=c.scenario,
                verdict=cd.verdict.value,
                evidence=(
                    f"run {diagnosis.run_id}",
                    f"cluster {c.id}: {c.n_trials} trials, {c.n_cases} cases",
                    *(f"{e.kind} {e.ref}" for e in c.examples[:3]),
                ),
                affected_share=share,
                affected_tickets_per_month=volume * share,
                severity=severity,
                cost_per_month=cost_month,
                fix=fix,
                fix_rate_lower=fix_lo,
                effort_weeks=weeks,
                effort_basis=item.why if item else "default estimate",
                confidence=confidence,
                expected_benefit_per_month=benefit,
                score=score,
                formula=FORMULA,
                validation_plan=(
                    f"Run the candidate with {fix} on the test split. The gates must "
                    "pass, and the cluster cases must go into the regression suite."
                    if fix
                    else "Collect more failed cases, then diagnose again."
                ),
                decision=decision,
                reason=reason,
            )
        )
    out.sort(key=lambda o: (-o.score, o.id))
    return out
