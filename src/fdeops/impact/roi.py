"""ROI with uncertainty. A Monte Carlo simulation samples each assumption from its range and each
measured rate from its posterior (a Dirichlet with a prior from the run-wide mix). The result is a
distribution, never one number."""

import math

import numpy as np

from fdeops.core.model import FrozenModel
from fdeops.impact.costs import Assumption, CostModel
from fdeops.impact.measure import RunMeasure

PRIOR_TRIALS = 2.0


class Distribution(FrozenModel):
    p5: float
    p50: float
    p95: float
    mean: float
    prob_positive: float

    @classmethod
    def of(cls, x: np.ndarray) -> "Distribution":
        finite = x[np.isfinite(x)]
        if finite.size == 0:
            return cls(p5=math.inf, p50=math.inf, p95=math.inf, mean=math.inf, prob_positive=0.0)
        p5, p50, p95 = (float(v) for v in np.percentile(finite, [5, 50, 95]))
        return cls(
            p5=p5, p50=p50, p95=p95, mean=float(finite.mean()), prob_positive=float((x > 0).mean())
        )


class ROIResult(FrozenModel):
    tenant_id: str
    run_id: str
    baseline_run_id: str | None
    draws: int
    measured: RunMeasure
    baseline: RunMeasure | None
    assumptions: CostModel
    human_cost_per_ticket: Distribution
    agent_cost_per_ticket: Distribution
    baseline_cost_per_ticket: Distribution | None
    monthly_savings_vs_human: Distribution
    monthly_savings_vs_baseline: Distribution | None
    payback_months: Distribution
    cost_per_automated_resolution: Distribution


def _tri(rng: np.random.Generator, a: Assumption, n: int) -> np.ndarray:
    if a.low == a.high:
        return np.full(n, a.likely)
    return rng.triangular(a.low, a.likely, a.high, n)


def _ticket_cost(
    m: RunMeasure,
    costs: CostModel,
    rng: np.random.Generator,
    n: int,
    rate: np.ndarray,
    rework: np.ndarray,
    triage: np.ndarray,
    critical: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Cost per ticket for the agent, for a person only, and the automation rate (each draw)."""
    total = sum(c.n_trials for c in m.categories)
    # Partial pooling: the prior of each category is the run-wide outcome mix with the weight of
    # PRIOR_TRIALS trials. A small category then stays near the run-wide rates, and a uniform prior
    # cannot invent a critical-error rate that the run did not show.
    pooled = np.array(
        [
            sum(c.resolved for c in m.categories),
            sum(c.escalated for c in m.categories),
            sum(c.failed for c in m.categories),
            sum(c.failed_critical for c in m.categories),
        ],
        float,
    )
    prior = PRIOR_TRIALS * pooled / max(float(pooled.sum()), 1.0) + 0.01
    agent = np.full(n, m.model_cost_per_ticket)
    human = np.zeros(n)
    automated = np.zeros(n)
    for c in m.categories:
        share = c.n_trials / total
        minutes = _tri(
            rng, costs.handling_minutes.get(c.category, costs.handling_minutes["default"]), n
        )
        counts = np.array([c.resolved, c.escalated, c.failed, c.failed_critical], float)
        p = rng.dirichlet(counts + prior, n)
        per_min = rate / 60
        human += share * minutes * per_min
        agent += share * (
            p[:, 1] * (minutes - triage).clip(0) * per_min
            + p[:, 2] * (minutes + rework) * per_min
            + p[:, 3] * ((minutes + rework) * per_min + critical)
        )
        automated += share * p[:, 0]
    return agent, human, automated


def simulate_roi(
    measured: RunMeasure,
    costs: CostModel,
    draws: int = 10_000,
    seed: int = 0,
    baseline: RunMeasure | None = None,
) -> ROIResult:
    rng = np.random.default_rng(seed)
    n = draws
    rate = _tri(rng, costs.staff_cost_per_hour, n)
    volume = _tri(rng, costs.monthly_ticket_volume, n) * _tri(rng, costs.adoption_rate, n)
    rework, triage = _tri(rng, costs.rework_minutes, n), _tri(rng, costs.triage_saving_minutes, n)
    critical = _tri(rng, costs.critical_error_cost, n)
    fixed = _tri(rng, costs.infrastructure_per_month, n) + _tri(rng, costs.maintenance_per_month, n)
    integration = _tri(rng, costs.integration_one_time, n)
    agent, human, automated = _ticket_cost(measured, costs, rng, n, rate, rework, triage, critical)
    savings = volume * (human - agent) - fixed
    payback = np.where(savings > 0, integration / np.maximum(savings, 1e-9), np.inf)
    per_resolution = (agent * volume + fixed) / np.maximum(volume * automated, 1e-9)
    base_cost = base_savings = None
    if baseline is not None:
        b_agent, _, _ = _ticket_cost(baseline, costs, rng, n, rate, rework, triage, critical)
        base_cost = Distribution.of(b_agent)
        base_savings = Distribution.of(volume * (b_agent - agent) - fixed)
    return ROIResult(
        tenant_id=measured.tenant_id,
        run_id=measured.run_id,
        baseline_run_id=baseline.run_id if baseline else None,
        draws=n,
        measured=measured,
        baseline=baseline,
        assumptions=costs,
        human_cost_per_ticket=Distribution.of(human),
        agent_cost_per_ticket=Distribution.of(agent),
        baseline_cost_per_ticket=base_cost,
        monthly_savings_vs_human=Distribution.of(savings),
        monthly_savings_vs_baseline=base_savings,
        payback_months=Distribution.of(payback),
        cost_per_automated_resolution=Distribution.of(per_resolution),
    )
