from fdeops.agent.config import AgentConfig, ModelRef
from fdeops.connectors.faults import FaultRule
from fdeops.diagnose.classify import classify, classify_run
from fdeops.diagnose.taxonomy import CAUSAL_ORDER, FailureClass
from fdeops.eval.runner import run_eval
from fdeops.llm.scripted import ScriptedLLM
from fdeops.llm.types import ToolCall
from fdeops.packs.billing.pack import BillingPack
from fdeops.tenancy.loader import Tenant
from fdeops.world.dataset import Dataset

from .conftest import STALE, run, subset

KNOW = BillingPack.knowledge_rules


def primaries(run_result) -> list[FailureClass]:  # type: ignore[no-untyped-def]
    return [lbl.primary for lbl in classify_run(run_result, KNOW)]


def test_success_has_no_label(tenant: Tenant, dev: Dataset) -> None:
    r = run(tenant, subset(dev, "refund_eligible"))
    assert all(t.success for t in r.results)
    assert classify_run(r, tenant.pack.knowledge_rules) == []
    assert classify(r.results[0], KNOW) is None


def test_stale_refund_is_stale_knowledge_not_policy(tenant: Tenant, dev: Dataset) -> None:
    r = run(tenant, subset(dev, tag="drift_sensitive"), config=STALE)
    labels = classify_run(r, tenant.pack.knowledge_rules)
    assert labels, "the stale index must cause failures on drift-sensitive cases"
    for lbl in labels:
        assert lbl.primary == FailureClass.STALE_KNOWLEDGE
        assert FailureClass.POLICY_VIOLATION in lbl.secondary
        kinds = {e.kind for e in lbl.evidence}
        assert {"stale_chunk", "violation"} <= kinds


def test_wrong_amount_is_bad_arguments(tenant: Tenant, dev: Dataset) -> None:
    r = run(tenant, subset(dev, "refund_eligible"), wrong_amount=1.0)
    assert set(primaries(r)) == {FailureClass.BAD_ARGUMENTS}


def test_injection_followed(tenant: Tenant, dev: Dataset) -> None:
    r = run(tenant, subset(dev, "injection_refund"), follow_injection=1.0)
    assert set(primaries(r)) == {FailureClass.INJECTION_FOLLOWED}


def test_missed_escalation(tenant: Tenant, dev: Dataset) -> None:
    r = run(tenant, subset(dev, "refund_over_limit"), miss_escalation=1.0)
    labels = classify_run(r, tenant.pack.knowledge_rules)
    assert labels and {lbl.primary for lbl in labels} == {FailureClass.MISSED_ESCALATION}
    assert all(FailureClass.POLICY_VIOLATION in lbl.secondary for lbl in labels)


def test_unhandled_tool_error(tenant: Tenant, dev: Dataset) -> None:
    faults = (FaultRule(op="lookup_customer", kind="error_5xx"),)
    r = run(tenant, subset(dev, "refund_eligible"), faults=faults)
    assert set(primaries(r)) == {FailureClass.UNHANDLED_TOOL_ERROR}
    lbl = classify_run(r, tenant.pack.knowledge_rules)[0]
    assert any(e.kind == "span" for e in lbl.evidence)


def test_budget_exhausted(tenant: Tenant, dev: Dataset) -> None:
    case = subset(dev, "invoice_explain")
    loop = ScriptedLLM(
        lambda req: ToolCall(
            id="x", name="search_kb", arguments={"query": "q"}, raw_arguments='{"query":"q"}'
        )
    )
    cfg = AgentConfig(id="loop", model=ModelRef(provider="scripted", name="s"), max_steps=3)
    r = run_eval(tenant, cfg, case, loop)
    assert set(primaries(r)) == {FailureClass.TIMEOUT_OR_BUDGET}


def test_every_failure_gets_a_label_with_evidence(tenant: Tenant, dev: Dataset) -> None:
    r = run(
        tenant,
        dev,
        wrong_amount=0.3,
        miss_escalation=0.3,
        follow_injection=0.5,
        ignore_retrieval=0.3,
        skip_lookup=0.2,
    )
    failed = [t for t in r.results if not t.success]
    labels = classify_run(r, tenant.pack.knowledge_rules)
    assert len(labels) == len(failed) > 0
    for lbl in labels:
        assert lbl.evidence, lbl
        assert lbl.primary not in lbl.secondary
        assert lbl.summary


def test_causal_order_is_total() -> None:
    assert set(CAUSAL_ORDER) == set(FailureClass)
    assert CAUSAL_ORDER[-1] == FailureClass.REASONING_ERROR


def test_stale_evidence_names_the_governing_section(tenant: Tenant, dev: Dataset) -> None:
    r = run(tenant, subset(dev, tag="drift_sensitive"), config=STALE)
    for lbl in classify_run(r, tenant.pack.knowledge_rules):
        chunks = [e.ref for e in lbl.evidence if e.kind == "stale_chunk"]
        assert chunks and all(c.startswith("refund-policy#refund-window@") for c in chunks)
