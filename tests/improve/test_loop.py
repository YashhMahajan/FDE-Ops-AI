from pathlib import Path

import pytest

from fdeops.core.errors import ConfigError
from fdeops.improve.loop import improve
from fdeops.release.gates import evaluate_gates
from fdeops.release.memo import render_memo
from fdeops.release.models import GateConfig, Release
from fdeops.release.registry import ReleaseRegistry
from fdeops.tenancy.loader import Tenant
from fdeops.world.dataset import Dataset

from ..release.conftest import CLEAN, STALE, run


@pytest.fixture
def production(tmp_path: Path, tenant: Tenant, gates: GateConfig, splits: dict[str, Dataset]):  # type: ignore[no-untyped-def]
    """v1 in production: the stale configuration (the state before the incident is fixed)."""
    registry = ReleaseRegistry(tmp_path / "releases", tenant.id)
    v1_test = run(tenant, splits["test"], STALE)
    results = [
        r.model_copy(update={"passed": True, "status": "pass"})
        for r in evaluate_gates(tenant, gates, v1_test, baseline=None)
    ]
    d = registry.propose(
        Release.from_run(tenant, gates, v1_test, "v1"), v1_test.run_id, None, results
    )
    registry.approve(d.decision_id, "sam", "approver", "initial", gates.approver_roles)
    return registry, v1_test


def test_improvement_loop_produces_pending_decision(
    tenant: Tenant, gates: GateConfig, splits: dict[str, Dataset], production
) -> None:  # type: ignore[no-untyped-def]
    registry, v1_test = production
    dev_run = run(tenant, splits["dev"], STALE)
    result = improve(
        tenant,
        gates,
        registry,
        dev_run,
        splits["dev"],
        splits["test"],
        v1_test,
        tenant.pack.heuristic_model(0, {}),
        version="v2",
    )
    assert result.status == "pending_approval", result.notes
    assert result.intervention_id in {"freshness_filter", "current_index_only"}
    assert result.dev_experiment is not None and result.dev_experiment["diff_mean"] > 0
    assert result.integration_passed and result.regression_passed
    d = registry.decision(result.decision_id)  # type: ignore[arg-type]
    assert d.status == "pending_approval" and d.gates_passed
    assert registry.production().version == "v1"  # type: ignore[union-attr]  (no auto-release)
    approved = registry.approve(d.decision_id, "sam", "approver", "fix", gates.approver_roles)
    assert registry.production().version == "v2"  # type: ignore[union-attr]
    assert set(d.regression_cases) <= set(registry.regression_cases())
    memo = render_memo(approved)
    assert ("approved" in memo and "freshness" in memo) or "current_index" in memo


def test_improvement_needs_dev_run(
    tenant: Tenant, gates: GateConfig, splits: dict[str, Dataset], production
) -> None:  # type: ignore[no-untyped-def]
    registry, v1_test = production
    with pytest.raises(ConfigError):
        improve(
            tenant,
            gates,
            registry,
            v1_test,
            splits["test"],
            splits["test"],
            v1_test,
            tenant.pack.heuristic_model(0, {}),
            version="v2",
        )


def test_no_fix_when_nothing_fails(
    tenant: Tenant, gates: GateConfig, splits: dict[str, Dataset], production
) -> None:  # type: ignore[no-untyped-def]
    registry, v1_test = production
    clean_dev = run(tenant, splits["dev"], CLEAN)
    result = improve(
        tenant,
        gates,
        registry,
        clean_dev,
        splits["dev"],
        splits["test"],
        v1_test,
        tenant.pack.heuristic_model(0, {}),
        version="v2",
    )
    assert result.status == "no_fix" and result.decision_id is None
