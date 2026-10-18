"""Measured outcomes of a run, for each cost category."""

import math
from collections import defaultdict

from fdeops.core.model import FrozenModel
from fdeops.core.provenance import Provenance
from fdeops.eval.report import summarize
from fdeops.eval.runner import RunResult
from fdeops.impact.costs import CostModel, category_of
from fdeops.release.models import Pricing


class CategoryMeasure(FrozenModel):
    category: str
    n_trials: int
    resolved: int
    """Correct, and the agent did the work without a person."""
    escalated: int
    """Correct, and a person must do the work."""
    failed: int
    failed_critical: int

    @property
    def share(self) -> float:
        return float(self.n_trials)


class RunMeasure(FrozenModel):
    run_id: str
    tenant_id: str
    provenance: Provenance
    n_trials: int
    categories: tuple[CategoryMeasure, ...]
    automation_rate: float
    escalation_rate: float
    critical_error_rate: float
    model_cost_per_ticket: float
    latency_p95_ms: float


def measure_run(run: RunResult, costs: CostModel, pricing: Pricing | None) -> RunMeasure:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in run.results:
        cat = category_of(r.tags, costs)
        out = r.score("outcome")
        escalated = bool(out and out.details.get("derived_resolution") == "escalated")
        critical = any(s.critical for s in r.scores)
        c = counts[cat]
        c["n"] += 1
        if r.success:
            c["escalated" if escalated else "resolved"] += 1
        else:
            c["failed_critical" if critical else "failed"] += 1
    cats = tuple(
        CategoryMeasure(
            category=k,
            n_trials=v["n"],
            resolved=v["resolved"],
            escalated=v["escalated"],
            failed=v["failed"],
            failed_critical=v["failed_critical"],
        )
        for k, v in sorted(counts.items())
    )
    n = len(run.results) or 1
    tokens_in = sum(r.episode.usage.input_tokens for r in run.results)
    tokens_out = sum(r.episode.usage.output_tokens for r in run.results)
    model_cost = (
        0.0
        if pricing is None
        else (
            tokens_in / 1e6 * pricing.usd_per_mtok_input
            + tokens_out / 1e6 * pricing.usd_per_mtok_output
        )
        / n
    )
    p95 = summarize(run).metrics.get("latency_p95_ms", math.nan)
    return RunMeasure(
        run_id=run.run_id,
        tenant_id=run.tenant_id,
        provenance=run.provenance,
        n_trials=n,
        categories=cats,
        automation_rate=sum(c.resolved for c in cats) / n,
        escalation_rate=sum(c.escalated for c in cats) / n,
        critical_error_rate=sum(c.failed_critical for c in cats) / n,
        model_cost_per_ticket=model_cost,
        latency_p95_ms=p95,
    )
