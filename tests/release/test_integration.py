import dataclasses

from fdeops.release.integration import run_integration_suite
from fdeops.release.shadow import shadow_compare
from fdeops.tenancy.loader import Tenant
from fdeops.world.dataset import Dataset

from .conftest import CLEAN, STALE


def test_integration_suite_passes_for_resilient_agent(
    tenant: Tenant, splits: dict[str, Dataset]
) -> None:
    report = run_integration_suite(
        tenant, CLEAN, splits["dev"], tenant.pack.heuristic_model(0, {}), sample=12
    )
    assert report.passed, [c for c in report.checks if not c.passed]
    names = {c.name for c in report.checks}
    assert {"no_crash", "no_duplicate_action", "audit_chain", "faults_injected"} <= names
    assert report.n_episodes >= 12 * 3


class NoIdempotency:
    """A pack whose APIs ignore idempotency keys: the suite must find the double actions."""

    def __init__(self, inner: object) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)

    def build_connectors(self, state: object) -> list[object]:
        out = []
        for c in self._inner.build_connectors(state):  # type: ignore[attr-defined]
            original = c.call

            def call(op, args, ctx, _orig=original):  # type: ignore[no-untyped-def]
                return _orig(op, args, dataclasses.replace(ctx, idempotency_key=None))

            c.call = call
            out.append(c)
        return out


def test_integration_suite_finds_duplicate_actions(
    tenant: Tenant, splits: dict[str, Dataset]
) -> None:
    broken = dataclasses.replace(tenant, pack=NoIdempotency(tenant.pack))
    report = run_integration_suite(
        broken, CLEAN, splits["dev"], tenant.pack.heuristic_model(0, {}), sample=12
    )
    dup = next(c for c in report.checks if c.name == "no_duplicate_action")
    assert not dup.passed and dup.failures


def test_shadow_mode_reports_disagreements(tenant: Tenant, splits: dict[str, Dataset]) -> None:
    traffic = splits["dev"]
    report = shadow_compare(
        tenant, traffic, production=CLEAN, candidate=STALE, llm=tenant.pack.heuristic_model(0, {})
    )
    assert report.n_cases == len(traffic.cases)
    assert 0 < report.agreement < 1
    assert report.disagreements
    assert all(
        d.production_success != d.candidate_success
        or d.production_resolution != d.candidate_resolution
        for d in report.disagreements
    )
