import pytest

from fdeops.core.errors import ConfigError
from fdeops.eval.runner import RunResult
from fdeops.release.gates import evaluate_gates
from fdeops.release.models import GateConfig
from fdeops.tenancy.loader import Tenant
from fdeops.world.dataset import Dataset

from .conftest import run


def by_gate(results):  # type: ignore[no-untyped-def]
    return {r.gate: r for r in results}


def test_every_gate_has_an_explanation(gates: GateConfig) -> None:
    for name, gate in gates.gates().items():
        assert gate.why.strip(), name


def test_missing_explanation_is_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from fdeops.release.models import load_gates

    p = tmp_path / "gates.yaml"
    p.write_text("task_success: {min_lower_limit: 0.8}\napprover_roles: [approver]\n")
    with pytest.raises(ConfigError) as exc:
        load_gates(p)
    assert "why" in str(exc.value)


def test_clean_candidate_passes_measurable_gates(
    tenant: Tenant, gates: GateConfig, clean_test: RunResult
) -> None:
    results = by_gate(evaluate_gates(tenant, gates, clean_test, baseline=None))
    for name in ("task_success", "critical_violations", "latency", "cost"):
        assert results[name].status == "pass", results[name]
    assert results["non_inferiority"].status == "not_applicable"  # first release: no baseline
    assert results["integration_suite"].status == "fail"  # required but not given
    assert results["judge_calibration"].status == "not_applicable"


def test_gates_refuse_dev_split(
    tenant: Tenant, gates: GateConfig, splits: dict[str, Dataset]
) -> None:
    dev_run = run(tenant, splits["dev"])
    with pytest.raises(ConfigError) as exc:
        evaluate_gates(tenant, gates, dev_run, baseline=None)
    assert "test split" in str(exc.value)


def test_stale_candidate_fails_success_and_critical(
    tenant: Tenant, gates: GateConfig, stale_test: RunResult, clean_test: RunResult
) -> None:
    results = by_gate(evaluate_gates(tenant, gates, stale_test, baseline=clean_test))
    assert results["critical_violations"].status == "fail"
    assert results["non_inferiority"].status == "fail"
    assert "refund" in results["non_inferiority"].observed


def test_slice_regression_fails_non_inferiority(
    tenant: Tenant, gates: GateConfig, splits: dict[str, Dataset], clean_test: RunResult
) -> None:
    # Only escalations become worse; the total can stay high.
    worse = run(tenant, splits["test"], miss_escalation=1.0)
    results = by_gate(evaluate_gates(tenant, gates, worse, baseline=clean_test))
    assert results["non_inferiority"].status == "fail"
    assert "escalation" in results["non_inferiority"].observed


def test_unmeasured_gate_fails_by_default(
    tenant: Tenant, gates: GateConfig, clean_test: RunResult
) -> None:
    no_price = gates.model_copy(update={"pricing": None})
    results = by_gate(evaluate_gates(tenant, no_price, clean_test, baseline=None))
    assert results["cost"].status == "not_measured" and not results["cost"].passed
    cost = no_price.cost.model_copy(update={"allow_unmeasured": True})  # type: ignore[union-attr]
    allowed = no_price.model_copy(update={"cost": cost})
    assert by_gate(evaluate_gates(tenant, allowed, clean_test, baseline=None))["cost"].passed


def test_baseline_must_use_same_dataset(
    tenant: Tenant, gates: GateConfig, clean_test: RunResult, splits: dict[str, Dataset]
) -> None:
    other = clean_test.model_copy(update={"dataset_hash": "sha256:" + "0" * 64})
    with pytest.raises(ConfigError):
        evaluate_gates(tenant, gates, clean_test, baseline=other)
