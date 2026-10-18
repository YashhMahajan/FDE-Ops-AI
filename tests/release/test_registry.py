from pathlib import Path

import pytest

from fdeops.core.errors import ConfigError
from fdeops.eval.runner import RunResult
from fdeops.release.gates import evaluate_gates
from fdeops.release.models import GateConfig, GateResult, Release
from fdeops.release.registry import ReleaseRegistry
from fdeops.tenancy.loader import Tenant


def passing(results: list[GateResult]) -> list[GateResult]:
    return [r.model_copy(update={"passed": True, "status": "pass"}) for r in results]


@pytest.fixture
def registry(tmp_path: Path) -> ReleaseRegistry:
    return ReleaseRegistry(tmp_path / "releases", "ledgerloop")


def propose(
    registry: ReleaseRegistry,
    tenant: Tenant,
    gates: GateConfig,
    run: RunResult,
    version: str,
    force_pass: bool = True,
):  # type: ignore[no-untyped-def]
    release = Release.from_run(tenant, gates, run, version)
    results = evaluate_gates(tenant, gates, run, baseline=registry.production_run_id and None)
    return registry.propose(release, run.run_id, None, passing(results) if force_pass else results)


def test_propose_approve_and_production_pointer(
    registry: ReleaseRegistry, tenant: Tenant, gates: GateConfig, clean_test: RunResult
) -> None:
    d = propose(registry, tenant, gates, clean_test, "v1")
    assert d.status == "pending_approval" and registry.production() is None
    approved = registry.approve(
        d.decision_id,
        approver="sam",
        role="approver",
        comment="ok",
        approver_roles=gates.approver_roles,
    )
    assert approved.status == "approved" and approved.approval is not None
    assert registry.production() is not None
    assert registry.production().release_id == d.release.release_id  # type: ignore[union-attr]


def test_gate_failure_rejects_without_approval(
    registry: ReleaseRegistry, tenant: Tenant, gates: GateConfig, stale_test: RunResult
) -> None:
    d = propose(registry, tenant, gates, stale_test, "bad", force_pass=False)
    assert d.status == "rejected_by_gates"
    with pytest.raises(ConfigError):
        registry.approve(
            d.decision_id,
            approver="sam",
            role="approver",
            comment="",
            approver_roles=gates.approver_roles,
        )
    assert registry.production() is None


def test_approval_needs_approver_role(
    registry: ReleaseRegistry, tenant: Tenant, gates: GateConfig, clean_test: RunResult
) -> None:
    d = propose(registry, tenant, gates, clean_test, "v1")
    with pytest.raises(ConfigError) as exc:
        registry.approve(
            d.decision_id,
            approver="eve",
            role="engineer",
            comment="",
            approver_roles=gates.approver_roles,
        )
    assert "approver" in str(exc.value)
    assert registry.production() is None


def test_rollback_and_history(
    registry: ReleaseRegistry,
    tenant: Tenant,
    gates: GateConfig,
    clean_test: RunResult,
    stale_test: RunResult,
) -> None:
    roles = gates.approver_roles
    d1 = propose(registry, tenant, gates, clean_test, "v1")
    registry.approve(d1.decision_id, "sam", "approver", "", roles)
    d2 = propose(registry, tenant, gates, stale_test, "v2")
    registry.approve(d2.decision_id, "sam", "approver", "", roles)
    assert registry.production().version == "v2"  # type: ignore[union-attr]
    back = registry.rollback("sam", "approver", "incident", roles)
    assert back.version == "v1" and registry.production().version == "v1"  # type: ignore[union-attr]
    assert [e.action for e in registry.history()] == ["approve", "approve", "rollback"]


def test_rollback_without_history_fails(registry: ReleaseRegistry, gates: GateConfig) -> None:
    with pytest.raises(ConfigError):
        registry.rollback("sam", "approver", "x", gates.approver_roles)
    assert registry.production() is None


def test_registry_persists(
    tmp_path: Path, tenant: Tenant, gates: GateConfig, clean_test: RunResult
) -> None:
    r1 = ReleaseRegistry(tmp_path / "rel", "ledgerloop")
    d = propose(r1, tenant, gates, clean_test, "v1")
    r1.approve(d.decision_id, "sam", "approver", "", gates.approver_roles)
    r2 = ReleaseRegistry(tmp_path / "rel", "ledgerloop")
    assert r2.production().version == "v1"  # type: ignore[union-attr]
    assert r2.decision(d.decision_id).status == "approved"


def test_release_bundle_hash_is_stable(
    tenant: Tenant, gates: GateConfig, clean_test: RunResult
) -> None:
    a = Release.from_run(tenant, gates, clean_test, "v1")
    b = Release.from_run(tenant, gates, clean_test, "v1")
    assert a.bundle_hash == b.bundle_hash and a.release_id == b.release_id
    other = Release.from_run(
        tenant, gates.model_copy(update={"approver_roles": ("x",)}), clean_test, "v1"
    )
    assert other.bundle_hash != a.bundle_hash
