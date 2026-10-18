from pathlib import Path

import pytest

from fdeops.core.errors import ConfigError
from fdeops.eval.runner import RunResult, run_eval
from fdeops.impact.baseline import faq_agent
from fdeops.impact.costs import CostModel, category_of, load_costs
from fdeops.impact.measure import measure_run
from fdeops.impact.report import render_roi
from fdeops.impact.roi import simulate_roi
from fdeops.tenancy.loader import Tenant
from fdeops.world.dataset import Dataset

from .conftest import CLEAN


def test_assumption_needs_range(tmp_path: Path) -> None:
    p = tmp_path / "costs.yaml"
    p.write_text(
        (Path(__file__).parents[2] / "tenants/ledgerloop/costs.yaml")
        .read_text()
        .replace("{low: 32, likely: 40, high: 52,", "{likely: 40,")
    )
    with pytest.raises(ConfigError):
        load_costs(p)
    p.write_text(
        (Path(__file__).parents[2] / "tenants/ledgerloop/costs.yaml")
        .read_text()
        .replace("{low: 32, likely: 40, high: 52,", "{low: 60, likely: 40, high: 52,")
    )
    with pytest.raises(ConfigError):
        load_costs(p)


def test_unknown_category_uses_default(costs: CostModel) -> None:
    assert category_of(("refund", "drift_sensitive"), costs) == "refund"
    assert category_of(("something_new",), costs) == "default"


def test_measure_counts_outcomes(
    clean_dev: RunResult, stale_dev: RunResult, costs: CostModel
) -> None:
    m = measure_run(clean_dev, costs, pricing=None)
    assert sum(c.n_trials for c in m.categories) == len(clean_dev.results)
    assert m.critical_error_rate == 0 and 0 < m.automation_rate <= 1
    s = measure_run(stale_dev, costs, pricing=None)
    refund = next(c for c in s.categories if c.category == "refund")
    assert refund.failed_critical > 0
    assert s.critical_error_rate > 0


def test_faq_baseline_is_measured_and_weaker(
    tenant: Tenant, dev: Dataset, clean_dev: RunResult, costs: CostModel
) -> None:
    base = run_eval(tenant, CLEAN, dev, None, external_agent=faq_agent)
    assert base.llm_provider == "external:faq_agent"
    b, a = measure_run(base, costs, None), measure_run(clean_dev, costs, None)
    assert b.automation_rate < a.automation_rate
    assert b.critical_error_rate == 0  # it never takes an action


def test_roi_distribution_and_baselines(
    tenant: Tenant, dev: Dataset, clean_dev: RunResult, stale_dev: RunResult, costs: CostModel
) -> None:
    base = run_eval(tenant, CLEAN, dev, None, external_agent=faq_agent)
    good = simulate_roi(
        measure_run(clean_dev, costs, None),
        costs,
        draws=4000,
        seed=1,
        baseline=measure_run(base, costs, None),
    )
    bad = simulate_roi(measure_run(stale_dev, costs, None), costs, draws=4000, seed=1)
    d = good.monthly_savings_vs_human
    assert d.p5 <= d.p50 <= d.p95 and 0 <= d.prob_positive <= 1
    assert good.monthly_savings_vs_human.p50 > bad.monthly_savings_vs_human.p50
    assert good.monthly_savings_vs_baseline is not None
    assert good.human_cost_per_ticket.p50 > good.agent_cost_per_ticket.p50
    again = simulate_roi(measure_run(clean_dev, costs, None), costs, draws=4000, seed=1)
    assert again.monthly_savings_vs_human == good.monthly_savings_vs_human  # seeded


def test_roi_report_keeps_pipeline_label(clean_dev: RunResult, costs: CostModel) -> None:
    from fdeops.devtools.ste import check_text, load_rules

    md = render_roi(simulate_roi(measure_run(clean_dev, costs, None), costs, draws=500))
    assert md.splitlines()[0].startswith("> **Provenance: pipeline-test")
    assert "assumption" in md and "measured" in md
    assert check_text(md, load_rules()) == []


def test_small_clean_categories_do_not_invent_critical_errors(
    clean_dev: RunResult, costs: CostModel
) -> None:
    # With a uniform prior, a category with 3 clean trials gets a 1-in-7 critical-error rate.
    # Partial pooling toward the run-wide mix keeps it near the measured value (zero here).
    roi = simulate_roi(measure_run(clean_dev, costs, None), costs, draws=4000, seed=2)
    assert roi.agent_cost_per_ticket.p50 < roi.human_cost_per_ticket.p50
