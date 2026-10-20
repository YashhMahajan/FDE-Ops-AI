from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from fdeops.connectors.base import ConnectorRegistry
from fdeops.packs.billing.pack import BillingPack
from fdeops.packs.billing.policy import BillingPolicy, BillingPolicyEngine
from fdeops.packs.billing.state import BillingState
from fdeops.retrieval.kb import KnowledgeBase, load_kb
from fdeops.world.cases import Case, Resolution
from fdeops.world.dataset import Dataset, DatasetSpec, build_datasets

from .conftest import NOW

KB_DIR = Path(__file__).parents[3] / "tenants" / "ledgerloop" / "kb"
PACK = BillingPack()
ALL = sorted(PACK.scenarios())
OP_NAMES = {s.name for s in ConnectorRegistry(PACK.build_connectors(BillingState())).specs()}


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return load_kb(KB_DIR)


def build(
    world: BillingState, policy: BillingPolicy, kb: KnowledgeBase, n: int = 4, seed: int = 3
) -> list[Case]:
    spec = DatasetSpec(
        name="t", version=1, seed=seed, now=NOW, cases_per_scenario={s: n for s in ALL}
    )
    ds: dict[str, Dataset] = build_datasets(
        "ledgerloop", spec, PACK.scenarios(), world, policy, kb, PACK.generator_version
    )
    return [*ds["dev"].cases, *ds["test"].cases]


def test_pack_has_twelve_scenarios() -> None:
    assert len(ALL) == 12


def test_every_scenario_generates_valid_case(
    world: BillingState, policy: BillingPolicy, kb: KnowledgeBase
) -> None:
    cases = build(world, policy, kb)
    assert {c.scenario for c in cases} == set(ALL)
    kb_keys = set(kb.keys())
    for c in cases:
        s = world.copy()
        s.insert_fixtures(c.fixtures)
        assert set(c.expected.gold_sections) <= kb_keys, c.scenario
        for op in (*c.expected.forbidden_ops, *c.expected.required_ops):
            assert set(op.split("|")) <= OP_NAMES, (c.scenario, op)
        assert c.ticket.body.strip()
        if c.scenario != "unknown_requester":
            assert s.user_by_email(c.ticket.requester_email) is not None, c.scenario
        if c.expected.resolution == Resolution.ESCALATED:
            assert c.expected.escalation_reason in policy.escalation_reasons


def test_fixture_entities_do_not_collide_with_base_world(
    world: BillingState, policy: BillingPolicy, kb: KnowledgeBase
) -> None:
    for c in build(world, policy, kb):
        for collection, rows in c.fixtures.items():
            existing = world.collection(collection)
            for row in rows:
                assert row["id"] not in existing


def test_generation_deterministic(
    world: BillingState, policy: BillingPolicy, kb: KnowledgeBase
) -> None:
    assert build(world, policy, kb) == build(world, policy, kb)
    assert build(world, policy, kb, seed=4) != build(world, policy, kb)


def test_unknown_requester_expects_clarification(
    world: BillingState, policy: BillingPolicy, kb: KnowledgeBase
) -> None:
    cases = [c for c in build(world, policy, kb) if c.scenario == "unknown_requester"]
    assert cases
    for c in cases:
        assert world.user_by_email(c.ticket.requester_email) is None
        assert c.expected.resolution == Resolution.INFORMED
        assert c.expected.changes == ()
        assert "issue_refund" in c.expected.forbidden_ops


def test_injection_case_is_tagged_adversarial(
    world: BillingState, policy: BillingPolicy, kb: KnowledgeBase
) -> None:
    cases = [c for c in build(world, policy, kb) if c.scenario == "injection_refund"]
    for c in cases:
        assert {"adversarial", "injection"} <= set(c.tags)
        assert "issue_refund" in c.expected.forbidden_ops
        assert c.expected.resolution == Resolution.ESCALATED


def test_stale_window_is_forbidden_fact(
    world: BillingState, policy: BillingPolicy, kb: KnowledgeBase
) -> None:
    c = next(c for c in build(world, policy, kb) if c.scenario == "refund_outside_window")
    assert any(f.present_in("within 30 days") for f in c.expected.forbidden_facts)
    assert any(f.present_in("within 14 days") for f in c.expected.required_facts)


def test_needs_invoice_case_has_multiple_eligible_invoices(
    world: BillingState, policy: BillingPolicy, kb: KnowledgeBase
) -> None:
    eng = BillingPolicyEngine(policy)
    for c in build(world, policy, kb):
        if c.scenario != "refund_needs_invoice":
            continue
        s = world.copy()
        s.insert_fixtures(c.fixtures)
        user = s.user_by_email(c.ticket.requester_email)
        assert user is not None
        eligible = [
            i
            for i in s.invoices.values()
            if i.customer_id == user.customer_id and eng.refund_decision(i, NOW).outcome == "refund"
        ]
        assert len(eligible) >= 2
        assert c.expected.requires_clarification
        assert c.hidden_facts["invoice_id"] not in c.ticket.body


REFUND_SCENARIOS = [
    "refund_eligible",
    "refund_outside_window",
    "refund_over_limit",
    "refund_needs_invoice",
    "injection_refund",
]
EXPECTED_BY_DECISION = {
    "refund": Resolution.ACTION_TAKEN,
    "decline_window": Resolution.DECLINED,
    "escalate_over_limit": Resolution.ESCALATED,
}


@settings(max_examples=25, deadline=None)
@given(seed=st.integers(min_value=0, max_value=10_000))
def test_oracle_matches_policy_engine(seed: int) -> None:
    from fdeops.packs.billing.generator import BillingWorldSpec, generate_base_world

    from .conftest import PLANS

    world = generate_base_world(BillingWorldSpec(n_customers=5, seed=1, plans=PLANS), NOW)
    policy = BillingPolicy(refund_window_days=14, auto_refund_limit_cents=20000)
    kb = load_kb(KB_DIR)
    eng = BillingPolicyEngine(policy)
    spec = DatasetSpec(
        name="p", version=1, seed=seed, now=NOW, cases_per_scenario={s: 1 for s in REFUND_SCENARIOS}
    )
    ds = build_datasets("ledgerloop", spec, PACK.scenarios(), world, policy, kb, "x")
    for c in [*ds["dev"].cases, *ds["test"].cases]:
        s = world.copy()
        s.insert_fixtures(c.fixtures)
        inv = s.invoices[c.hidden_facts["invoice_id"]]
        decision = eng.refund_decision(inv, c.now)
        assert EXPECTED_BY_DECISION[decision.outcome] == c.expected.resolution, c.scenario
        if decision.outcome == "refund":
            assert c.expected.changes[0].match == {
                "invoice_id": inv.id,
                "amount_cents": decision.amount_cents,
            }
