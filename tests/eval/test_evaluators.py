from typing import Any

import pytest

from fdeops.agent.config import AgentConfig, ModelRef
from fdeops.agent.episode import EpisodeResult, run_episode
from fdeops.eval.evaluators import (
    DEFAULT_EVALUATORS,
    ClarificationEvaluator,
    EscalationEvaluator,
    FactsEvaluator,
    InjectionEvaluator,
    OutcomeEvaluator,
    PerfEvaluator,
    PolicyEvaluator,
    RetrievalEvaluator,
    ToolUseEvaluator,
    trial_success,
)
from fdeops.eval.types import EvalContext, Score
from fdeops.retrieval.retriever import RetrievalConfig
from fdeops.tenancy.loader import Tenant
from fdeops.world.cases import Case

from ..agent.conftest import call, first, script

HEURISTIC = AgentConfig(
    id="h",
    model=ModelRef(provider="heuristic", name="h"),
    retrieval=RetrievalConfig(include_superseded=False),
)


def heuristic(tenant: Tenant, case: Case, **errors: float) -> EpisodeResult:
    return run_episode(case, tenant, HEURISTIC, tenant.pack.heuristic_model(0, errors), trial=0)


def scripted(tenant: Tenant, case: Case, config: AgentConfig, *steps: Any) -> EpisodeResult:
    return run_episode(case, tenant, config, script(list(steps)), trial=0)


def by_name(scores: list[Score]) -> dict[str, Score]:
    return {s.name: s for s in scores}


def reply(case: Case, msg: str) -> Any:
    return lambda r: call("reply_to_customer", ticket_id=case.ticket.ticket_id, message=msg)


@pytest.fixture
def ctx(tenant: Tenant) -> EvalContext:
    return EvalContext(tenant=tenant)


def test_outcome_pass_and_fail(
    tenant: Tenant, cases: list[Case], ctx: EvalContext, config: AgentConfig
) -> None:
    case = first(cases, "refund_eligible")
    good = OutcomeEvaluator().evaluate(case, heuristic(tenant, case), ctx)[0]
    assert good.passed is True
    lazy = scripted(tenant, case, config, reply(case, "Sorry, no."))
    bad = OutcomeEvaluator().evaluate(case, lazy, ctx)[0]
    assert bad.passed is False
    assert bad.details["missing"]


def test_outcome_unexpected_action_fails(
    tenant: Tenant, cases: list[Case], ctx: EvalContext, config: AgentConfig
) -> None:
    case = first(cases, "export_unauthorized")
    ep = scripted(
        tenant,
        case,
        config,
        lambda r: call("lookup_customer", email=case.ticket.requester_email),
        lambda r: call(
            "request_data_export",
            customer_id=case.fixtures["customers"][0]["id"],
            requester_email=case.ticket.requester_email,
        ),
        reply(case, "done"),
    )
    score = OutcomeEvaluator().evaluate(case, ep, ctx)[0]
    assert score.passed is False and score.details["unexpected"]


def test_outcome_informed_requires_a_message(
    tenant: Tenant, cases: list[Case], ctx: EvalContext, config: AgentConfig
) -> None:
    case = first(cases, "payment_failed_help")
    looped = run_episode(
        case,
        tenant,
        config.model_copy(update={"max_steps": 2}),
        script([lambda r: call("search_kb", query="x")]),
        trial=0,
    )
    assert OutcomeEvaluator().evaluate(case, looped, ctx)[0].passed is False


def test_tool_use_required_and_forbidden(
    tenant: Tenant, cases: list[Case], ctx: EvalContext, config: AgentConfig
) -> None:
    case = first(cases, "invoice_explain")
    good = by_name(ToolUseEvaluator().evaluate(case, heuristic(tenant, case), ctx))
    assert good["tool_use"].passed is True
    skipped = scripted(tenant, case, config, reply(case, "It's a subscription."))
    bad = by_name(ToolUseEvaluator().evaluate(case, skipped, ctx))
    assert bad["tool_use"].passed is False
    assert bad["tool_use"].details["missing_required"] == ["get_invoice|list_invoices"]


def test_policy_violation_is_critical(
    tenant: Tenant, cases: list[Case], ctx: EvalContext, config: AgentConfig
) -> None:
    case = first(cases, "refund_outside_window")
    inv = case.hidden_facts["invoice_id"]
    ep = scripted(
        tenant,
        case,
        config,
        lambda r: call("issue_refund", invoice_id=inv, amount_cents=100, reason="x"),
        reply(case, "done"),
    )
    score = PolicyEvaluator().evaluate(case, ep, ctx)[0]
    assert score.passed is False and score.critical
    assert "refund.outside_window" in score.details["rules"]
    clean = PolicyEvaluator().evaluate(case, heuristic(tenant, case), ctx)[0]
    assert clean.passed is True and not clean.critical


def test_escalation_confusion_cells(
    tenant: Tenant, cases: list[Case], ctx: EvalContext, config: AgentConfig
) -> None:
    case = first(cases, "refund_over_limit")
    tp = EscalationEvaluator().evaluate(case, heuristic(tenant, case), ctx)[0]
    assert tp.passed and tp.details["cell"] == "tp"
    fn = EscalationEvaluator().evaluate(
        case, scripted(tenant, case, config, reply(case, "no")), ctx
    )[0]
    assert fn.passed is False and fn.details["cell"] == "fn"
    other = first(cases, "payment_failed_help")
    fp_ep = scripted(
        tenant,
        other,
        config,
        lambda r: call(
            "escalate_to_human", ticket_id=other.ticket.ticket_id, reason_code="other", note="?"
        ),
    )
    fp = EscalationEvaluator().evaluate(other, fp_ep, ctx)[0]
    assert fp.passed is False and fp.details["cell"] == "fp"
    wrong_reason = scripted(
        tenant,
        case,
        config,
        lambda r: call(
            "escalate_to_human", ticket_id=case.ticket.ticket_id, reason_code="other", note="?"
        ),
    )
    wr = EscalationEvaluator().evaluate(case, wrong_reason, ctx)[0]
    assert wr.passed is False and wr.details["cell"] == "tp" and not wr.details["reason_match"]


def test_retrieval_metrics(tenant: Tenant, cases: list[Case], ctx: EvalContext) -> None:
    case = first(cases, "payment_failed_help")
    s = by_name(RetrievalEvaluator().evaluate(case, heuristic(tenant, case), ctx))
    d = s["retrieval.recall"].details
    gold, missing, keys = d["gold"], d["missing"], d["retrieved"]
    assert s["retrieval.recall"].value == (len(gold) - len(missing)) / len(gold)
    first_gold = next(i for i, k in enumerate(keys, start=1) if k in gold)
    assert s["retrieval.mrr"].value == 1 / first_gold
    assert 0 < s["retrieval.ndcg"].value <= 1.0
    assert s["retrieval.stale_hit"].value == 0.0


def test_retrieval_detects_stale_hits(tenant: Tenant, cases: list[Case], ctx: EvalContext) -> None:
    case = first(cases, "refund_outside_window")
    cfg = HEURISTIC.model_copy(update={"retrieval": RetrievalConfig(include_superseded=True)})
    ep = run_episode(case, tenant, cfg, tenant.pack.heuristic_model(0, {}), trial=0)
    s = by_name(RetrievalEvaluator().evaluate(case, ep, ctx))
    assert s["retrieval.stale_hit"].value == 1.0


def test_facts_required_and_forbidden(
    tenant: Tenant, cases: list[Case], ctx: EvalContext, config: AgentConfig
) -> None:
    case = first(cases, "refund_outside_window")
    good = scripted(tenant, case, config, reply(case, "Refunds are possible within 14 days."))
    assert FactsEvaluator().evaluate(case, good, ctx)[0].passed is True
    stale = scripted(tenant, case, config, reply(case, "Refunds are possible within 30 days."))
    score = FactsEvaluator().evaluate(case, stale, ctx)[0]
    assert score.passed is False
    assert score.details["forbidden_present"] == ["stale_window_30"]
    assert score.details["missing"] == ["refund_window"]


def test_injection_only_on_tagged_cases(
    tenant: Tenant, cases: list[Case], ctx: EvalContext
) -> None:
    plain = first(cases, "refund_eligible")
    assert InjectionEvaluator().evaluate(plain, heuristic(tenant, plain), ctx) == []
    case = first(cases, "injection_refund")
    ok = InjectionEvaluator().evaluate(case, heuristic(tenant, case), ctx)[0]
    assert ok.passed is True
    hacked = InjectionEvaluator().evaluate(
        case, heuristic(tenant, case, follow_injection=1.0), ctx
    )[0]
    assert hacked.passed is False and hacked.critical


def test_clarification(
    tenant: Tenant, cases: list[Case], ctx: EvalContext, config: AgentConfig
) -> None:
    case = first(cases, "refund_needs_invoice")
    asked = ClarificationEvaluator().evaluate(case, heuristic(tenant, case), ctx)[0]
    assert asked.passed is True
    inv = case.hidden_facts["invoice_id"]
    amount = case.expected.changes[0].match["amount_cents"]
    guessed = scripted(
        tenant,
        case,
        config,
        lambda r: call("issue_refund", invoice_id=inv, amount_cents=amount, reason="x"),
        reply(case, "done"),
    )
    assert ClarificationEvaluator().evaluate(case, guessed, ctx)[0].passed is False
    other = first(cases, "refund_eligible")
    assert ClarificationEvaluator().evaluate(other, heuristic(tenant, other), ctx) == []


def test_perf_reports_numbers(tenant: Tenant, cases: list[Case], ctx: EvalContext) -> None:
    case = first(cases, "refund_eligible")
    s = by_name(PerfEvaluator().evaluate(case, heuristic(tenant, case), ctx))
    assert s["perf.latency_ms"].value > 0
    assert s["perf.input_tokens"].value > 0
    assert s["perf.steps"].value >= 3
    assert all(x.passed is None for x in s.values())


def test_trial_success_combines(tenant: Tenant, cases: list[Case], ctx: EvalContext) -> None:
    case = first(cases, "refund_eligible")
    ep = heuristic(tenant, case)
    scores = [s for e in DEFAULT_EVALUATORS for s in e.evaluate(case, ep, ctx)]
    assert trial_success(scores)
    bad = heuristic(tenant, case, wrong_amount=1.0)
    scores = [s for e in DEFAULT_EVALUATORS for s in e.evaluate(case, bad, ctx)]
    assert not trial_success(scores)
