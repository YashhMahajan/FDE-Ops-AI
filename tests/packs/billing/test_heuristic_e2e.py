from pathlib import Path

import pytest

from fdeops.agent.config import AgentConfig, ModelRef
from fdeops.agent.episode import EpisodeResult, run_episode
from fdeops.retrieval.retriever import RetrievalConfig
from fdeops.tenancy.loader import Tenant, load_tenant
from fdeops.world.cases import Case
from fdeops.world.state import get_path

LEDGERLOOP = Path(__file__).parents[3] / "tenants" / "ledgerloop"
FRESH = RetrievalConfig(include_superseded=False, index_as_of=None)
STALE = RetrievalConfig(include_superseded=True)


@pytest.fixture(scope="module")
def tenant() -> Tenant:
    return load_tenant(LEDGERLOOP)


@pytest.fixture(scope="module")
def cases(tenant: Tenant) -> list[Case]:
    ds = tenant.build_datasets("support-core")
    return [*ds["dev"].cases, *ds["test"].cases]


def config(retrieval: RetrievalConfig) -> AgentConfig:
    return AgentConfig(
        id="h",
        model=ModelRef(provider="heuristic", name="heuristic-billing-1"),
        retrieval=retrieval,
    )


def outcome_ok(tenant: Tenant, case: Case, ep: EpisodeResult) -> bool:
    actual = [c for c in ep.changes if tenant.pack.is_outcome_change(c)]
    unmatched = list(actual)
    for exp in case.expected.changes:
        hit = next(
            (
                c
                for c in unmatched
                if c.collection == exp.collection
                and c.kind == exp.kind
                and all(get_path(c.after, k) == v for k, v in exp.match.items())
            ),
            None,
        )
        if hit is None:
            return False
        unmatched.remove(hit)
    called = {t.op for t in ep.tool_calls if t.ok}
    return not unmatched and not (called & set(case.expected.forbidden_ops))


def test_heuristic_is_a_pack_model(tenant: Tenant) -> None:
    llm = tenant.pack.heuristic_model(seed=0, error_rates={})
    assert llm.provider == "heuristic"
    with pytest.raises(ValueError):
        tenant.pack.heuristic_model(seed=0, error_rates={"made_up": 1.0})


def test_heuristic_solves_clean_cases_without_errors(tenant: Tenant, cases: list[Case]) -> None:
    llm = tenant.pack.heuristic_model(seed=0, error_rates={})
    results = [(c, run_episode(c, tenant, config(FRESH), llm, trial=0)) for c in cases]
    failed = [c.scenario for c, ep in results if not outcome_ok(tenant, c, ep)]
    assert len(failed) / len(cases) <= 0.10, failed
    assert all(ep.error is None for _, ep in results)


def test_stale_index_causes_window_errors(tenant: Tenant, cases: list[Case]) -> None:
    llm = tenant.pack.heuristic_model(seed=0, error_rates={})
    drift = [c for c in cases if "drift_sensitive" in c.tags]
    assert drift
    eps = [run_episode(c, tenant, config(STALE), llm, trial=0) for c in drift]
    refunded = [ep for ep in eps if any(ch.collection == "refunds" for ch in ep.changes)]
    assert refunded, "a stale 30-day window in the index should cause wrongful refunds"
    assert all("refund.outside_window" in {v.rule for v in ep.violations} for ep in refunded)
    assert any(chunk.stale for ep in refunded for chunk in ep.retrieved)


def test_error_modes_cause_failures(tenant: Tenant, cases: list[Case]) -> None:
    clean = tenant.pack.heuristic_model(seed=0, error_rates={})
    buggy = tenant.pack.heuristic_model(
        seed=0, error_rates={"wrong_amount": 1.0, "follow_injection": 1.0}
    )
    refund = [c for c in cases if c.scenario in ("refund_eligible", "injection_refund")][:10]
    ok_clean = sum(
        outcome_ok(tenant, c, run_episode(c, tenant, config(FRESH), clean, 0)) for c in refund
    )
    ok_buggy = sum(
        outcome_ok(tenant, c, run_episode(c, tenant, config(FRESH), buggy, 0)) for c in refund
    )
    assert ok_buggy < ok_clean


def test_heuristic_deterministic(tenant: Tenant, cases: list[Case]) -> None:
    llm = tenant.pack.heuristic_model(seed=3, error_rates={"wrong_amount": 0.5})
    c = next(c for c in cases if c.scenario == "refund_eligible")
    a = run_episode(c, tenant, config(FRESH), llm, trial=1)
    b = run_episode(c, tenant, config(FRESH), llm, trial=1)
    assert a.changes == b.changes and [t.op for t in a.tool_calls] == [t.op for t in b.tool_calls]
