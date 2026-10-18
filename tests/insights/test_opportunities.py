from pathlib import Path

import pytest

from fdeops.core.errors import ConfigError
from fdeops.diagnose.interventions import diagnose_run
from fdeops.impact.measure import measure_run
from fdeops.insights.opportunities import build_opportunities, load_effort
from fdeops.insights.roadmap import render_roadmap

ROOT = Path(__file__).parents[2]


def test_effort_must_be_positive(tmp_path: Path) -> None:
    p = tmp_path / "effort.yaml"
    p.write_text("interventions:\n  freshness_filter: {weeks: 0, why: x}\ndefault_weeks: 2\n")
    with pytest.raises(ConfigError):
        load_effort(p)


def test_opportunities_ranked_with_visible_formula(tenant, dev, stale_dev, costs) -> None:  # type: ignore[no-untyped-def]
    diagnosis = diagnose_run(tenant, stale_dev, dev, tenant.pack.heuristic_model(0, {}))
    effort = load_effort(ROOT / "tenants/ledgerloop/effort.yaml")
    opps = build_opportunities(
        stale_dev, diagnosis, measure_run(stale_dev, costs, None), costs, effort
    )
    assert opps and opps == sorted(opps, key=lambda o: -o.score)
    top = opps[0]
    assert top.failure_class == "stale_knowledge" and top.decision == "build"
    assert top.fix in {"freshness_filter", "current_index_only"}
    assert top.expected_benefit_per_month > 0 and top.effort_weeks > 0
    assert "expected_benefit" in top.formula and top.evidence
    md = render_roadmap(opps, tenant.id)
    from fdeops.devtools.ste import check_text, load_rules

    assert check_text(md, load_rules()) == []
    assert "We do not build" in md or "do not build" in md


def test_inconclusive_goes_to_not_build(tenant, dev, stale_dev, costs) -> None:  # type: ignore[no-untyped-def]
    diagnosis = diagnose_run(tenant, stale_dev, dev, tenant.pack.heuristic_model(0, {}))
    effort = load_effort(ROOT / "tenants/ledgerloop/effort.yaml")
    opps = build_opportunities(
        stale_dev, diagnosis, measure_run(stale_dev, costs, None), costs, effort
    )
    for o in opps:
        if o.verdict == "inconclusive":
            assert o.decision == "not build" and o.confidence <= 0.2
