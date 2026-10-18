from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from fdeops.agent.config import AgentConfig, ModelRef
from fdeops.connectors.base import ConnectorRegistry, ErrorCode, OpContext
from fdeops.core.clock import FakeClock
from fdeops.core.hashing import content_hash
from fdeops.eval.runner import run_eval
from fdeops.packs.logistics.entities import Account, Shipment, User
from fdeops.packs.logistics.generator import LogisticsWorldSpec, generate_base_world
from fdeops.packs.logistics.ops import AGENT_SCOPES, build_logistics_connectors
from fdeops.packs.logistics.pack import LogisticsPack
from fdeops.packs.logistics.policy import LogisticsPolicy, LogisticsPolicyEngine
from fdeops.packs.logistics.state import LogisticsState
from fdeops.retrieval.retriever import RetrievalConfig
from fdeops.tenancy.loader import Tenant, load_tenant
from fdeops.world.cases import Resolution
from fdeops.world.dataset import Dataset, DatasetSpec, build_datasets

ROOT = Path(__file__).parents[3]
NOW = datetime(2026, 9, 20, 10, tzinfo=UTC)
POLICY = LogisticsPolicy()
FRESH = AgentConfig(
    id="h",
    model=ModelRef(provider="heuristic", name="h"),
    retrieval=RetrievalConfig(include_superseded=False),
)
STALE = FRESH.model_copy(
    update={"id": "stale", "retrieval": RetrievalConfig(include_superseded=True)}
)


@pytest.fixture(scope="module")
def tenant() -> Tenant:
    return load_tenant(ROOT / "tenants/parcelpoint")


@pytest.fixture(scope="module")
def data(tenant: Tenant) -> dict[str, Dataset]:
    return tenant.build_datasets("support-core")


def test_world_deterministic_and_unique_tracking() -> None:
    spec = LogisticsWorldSpec(seed=5, n_accounts=20)
    a, b = generate_base_world(spec, NOW), generate_base_world(spec, NOW)
    assert content_hash(a) == content_hash(b)
    tns = [s.tracking_number for s in a.shipments.values()]
    assert len(tns) == len(set(tns)) == 60


def _state() -> LogisticsState:
    s = LogisticsState()
    s.upsert("accounts", Account(id="a1", company="A", tier="standard", created_at=NOW))
    s.upsert("users", User(id="u1", account_id="a1", email="o@a.example", name="O", role="owner"))
    s.upsert(
        "shipments",
        Shipment(
            id="s1",
            account_id="a1",
            tracking_number="PP123456789",
            status="delivered",
            origin_city="Lyon",
            destination_address="1 Mill Road, Lyon",
            recipient_name="R",
            recipient_phone="+31 6 123 4567",
            declared_value_cents=40000,
            shipped_at=NOW - timedelta(days=5),
            eta=NOW.date(),
            delivered_at=NOW - timedelta(days=2),
        ),
    )
    return s


def test_claim_api_is_idempotent_and_checks_declared_value() -> None:
    s = _state()
    reg = ConnectorRegistry(build_logistics_connectors(s))
    ctx = OpContext(
        tenant_id="p", actor="agent", scopes=AGENT_SCOPES, clock=FakeClock(NOW), idempotency_key="k"
    )
    args = {"shipment_id": "s1", "kind": "damage", "amount_cents": 1000, "description": "x"}
    assert reg.call("file_claim", args, ctx).ok
    assert reg.call("file_claim", args, ctx).data["duplicate"] is True
    assert len(s.claims) == 1
    over = reg.call(
        "file_claim",
        {**args, "amount_cents": 50000},
        OpContext(tenant_id="p", actor="agent", scopes=AGENT_SCOPES, clock=FakeClock(NOW)),
    )
    assert over.error is not None and over.error.code == ErrorCode.CONFLICT


def test_address_change_after_delivery_conflicts() -> None:
    s = _state()
    reg = ConnectorRegistry(build_logistics_connectors(s))
    ctx = OpContext(tenant_id="p", actor="agent", scopes=AGENT_SCOPES, clock=FakeClock(NOW))
    r = reg.call(
        "update_delivery_address", {"shipment_id": "s1", "new_address": "2 Mill Road, X"}, ctx
    )
    assert r.error is not None and r.error.code == ErrorCode.CONFLICT


def test_claim_decision_boundaries() -> None:
    eng = LogisticsPolicyEngine(POLICY)
    s = _state().shipments["s1"]
    assert eng.claim_decision(s, "damage", 30000, NOW).outcome == "approve"
    assert eng.claim_decision(s, "damage", 30001, NOW).outcome == "escalate_over_limit"
    assert eng.claim_decision(s, "damage", 40001, NOW).outcome == "decline_over_value"
    late = s.model_copy(update={"delivered_at": NOW - timedelta(days=31)})
    assert eng.claim_decision(late, "damage", 100, NOW).outcome == "decline_window"
    edge = s.model_copy(update={"delivered_at": NOW - timedelta(days=30)})
    assert eng.claim_decision(edge, "damage", 100, NOW).outcome == "approve"
    assert eng.claim_decision(s, "loss", 100, NOW).outcome == "decline_status"


def test_policy_check_flags_too_late_address_change() -> None:
    s = _state()
    s.upsert("shipments", s.shipments["s1"].model_copy(update={"status": "out_for_delivery"}))
    v = LogisticsPolicyEngine(POLICY).check(
        "update_delivery_address", {"shipment_id": "s1"}, s, "o@a.example", NOW
    )
    assert [x.rule for x in v] == ["address.too_late"]


def test_tenant_is_different_from_ledgerloop(tenant: Tenant) -> None:
    ledger = load_tenant(ROOT / "tenants/ledgerloop")
    assert tenant.pack.id == "logistics" and ledger.pack.id == "billing"
    assert tenant.config.pii.redact and not ledger.config.pii.redact
    assert tenant.scopes != ledger.scopes


def test_every_scenario_valid(tenant: Tenant, data: dict[str, Dataset]) -> None:
    cases = [*data["dev"].cases, *data["test"].cases]
    assert {c.scenario for c in cases} == set(LogisticsPack().scenarios())
    ops = {
        s.name
        for s in ConnectorRegistry(LogisticsPack().build_connectors(LogisticsState())).specs()
    }
    for c in cases:
        assert set(c.expected.gold_sections) <= set(tenant.kb.keys()), c.scenario
        for op in (*c.expected.forbidden_ops, *c.expected.required_ops):
            assert set(op.split("|")) <= ops
    assert any("drift_sensitive" in c.tags for c in cases)


@settings(max_examples=15, deadline=None)
@given(seed=st.integers(0, 10_000))
def test_oracle_agrees_with_policy_engine(seed: int) -> None:
    t = load_tenant(ROOT / "tenants/parcelpoint")
    spec = DatasetSpec(
        name="p",
        version=1,
        seed=seed,
        now=NOW,
        cases_per_scenario={
            "damage_claim_small": 1,
            "damage_claim_large": 1,
            "claim_outside_window": 1,
        },
    )
    ds = build_datasets("parcelpoint", spec, t.pack.scenarios(), t.base_world, t.policy, t.kb, "x")
    eng = LogisticsPolicyEngine(t.policy)
    mapping = {
        "approve": Resolution.ACTION_TAKEN,
        "escalate_over_limit": Resolution.ESCALATED,
        "decline_window": Resolution.DECLINED,
    }
    for c in [*ds["dev"].cases, *ds["test"].cases]:
        s = Shipment.model_validate(c.fixtures["shipments"][0])
        amount = next(
            (ch.match["amount_cents"] for ch in c.expected.changes if ch.collection == "claims"),
            None,
        )
        if amount is None:
            import re

            amount = round(
                float(re.findall(r"\$([\d,]+\.\d\d)", c.ticket.body)[0].replace(",", "")) * 100
            )
        assert (
            mapping[eng.claim_decision(s, "damage", amount, c.now).outcome] == c.expected.resolution
        )


def test_heuristic_clean_success_is_high(tenant: Tenant, data: dict[str, Dataset]) -> None:
    run = run_eval(tenant, FRESH, data["dev"], tenant.pack.heuristic_model(0, {}))
    failed = [r.scenario for r in run.results if not r.success]
    assert len(failed) / len(run.results) <= 0.10, failed


def test_stale_claim_limit_causes_wrongful_approvals(
    tenant: Tenant, data: dict[str, Dataset]
) -> None:
    drift = data["test"].model_copy(
        update={"cases": tuple(c for c in data["test"].cases if "drift_sensitive" in c.tags)}
    )
    run = run_eval(tenant, STALE, drift, tenant.pack.heuristic_model(0, {}))
    wrong = [r for r in run.results if any(ch.collection == "claims" for ch in r.episode.changes)]
    assert wrong
    assert all("claim.over_auto_limit" in {v.rule for v in r.episode.violations} for r in wrong)


def test_parcelpoint_runs_store_no_addresses(
    tenant: Tenant, data: dict[str, Dataset], tmp_path: Path
) -> None:
    from fdeops.eval.report import save_run

    sub = data["dev"].model_copy(
        update={
            "cases": tuple(c for c in data["dev"].cases if c.scenario == "address_change_allowed")
        }
    )
    run = run_eval(tenant, FRESH, sub, tenant.pack.heuristic_model(0, {}))
    assert all(r.success for r in run.results)
    stored = (save_run(run, tmp_path) / "run.json").read_text()
    assert not any(c.hidden_facts["new_address"] in stored for c in sub.cases)
