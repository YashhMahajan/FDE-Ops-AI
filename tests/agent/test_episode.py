import json

from fdeops.agent.config import AgentConfig
from fdeops.agent.episode import run_episode
from fdeops.agent.support_agent import TurnOutcome
from fdeops.connectors.faults import FaultRule
from fdeops.llm.scripted import ScriptedLLM
from fdeops.llm.types import ToolCall
from fdeops.tenancy.loader import Tenant
from fdeops.world.cases import Case

from .conftest import call, first, script, tool_results


def refund_script(case: Case) -> ScriptedLLM:
    inv = case.hidden_facts["invoice_id"]
    amount = case.expected.changes[0].match["amount_cents"]
    return script(
        [
            lambda r: call("lookup_customer", email=case.ticket.requester_email),
            lambda r: call(
                "issue_refund", invoice_id=inv, amount_cents=amount, reason="customer asked"
            ),
            lambda r: call(
                "reply_to_customer",
                ticket_id=case.ticket.ticket_id,
                message=f"Refunded ${amount / 100:.2f}.",
            ),
        ]
    )


def test_happy_path_refund_episode(tenant: Tenant, cases: list[Case], config: AgentConfig) -> None:
    case = first(cases, "refund_eligible")
    ep = run_episode(case, tenant, config, refund_script(case), trial=0)
    assert ep.outcome == TurnOutcome.REPLY
    assert ep.error is None
    refunds = [c for c in ep.changes if c.collection == "refunds"]
    assert len(refunds) == 1 and refunds[0].after is not None
    assert refunds[0].after["invoice_id"] == case.hidden_facts["invoice_id"]
    assert [t.op for t in ep.tool_calls] == ["lookup_customer", "issue_refund", "reply_to_customer"]
    assert ep.final_message.startswith("Refunded")
    assert ep.violations == ()
    assert ep.audit_ok
    assert ep.retrieved, "auto-context retrieval should have run"
    kinds = {s.kind for s in ep.trace.spans}
    assert {"agent", "turn", "llm", "tool", "retrieval"} <= {str(k) for k in kinds}


def test_episode_is_isolated_from_tenant_world(
    tenant: Tenant, cases: list[Case], config: AgentConfig
) -> None:
    case = first(cases, "refund_eligible")
    before = len(tenant.base_world.collection("refunds"))
    run_episode(case, tenant, config, refund_script(case), trial=0)
    assert len(tenant.base_world.collection("refunds")) == before


def test_malformed_tool_call_is_observation_not_crash(
    tenant: Tenant, cases: list[Case], config: AgentConfig
) -> None:
    case = first(cases, "invoice_explain")
    bad_json = ToolCall(id="b1", name="get_invoice", arguments=None, raw_arguments="{oops")
    seen: list[list[dict]] = []

    def finish(r):  # type: ignore[no-untyped-def]
        seen.append(tool_results(r))
        return call("reply_to_customer", ticket_id=case.ticket.ticket_id, message="ok")

    llm = script(
        [
            lambda r: bad_json,
            lambda r: call("no_such_tool", x=1),
            lambda r: call("get_invoice", invoice_id=123),
            finish,
        ]
    )
    ep = run_episode(case, tenant, config, llm, trial=0)
    assert ep.outcome == TurnOutcome.REPLY
    errors = [res["error"]["code"] for res in seen[0]]
    assert errors == ["INVALID_ARGUMENT", "INVALID_ARGUMENT", "INVALID_ARGUMENT"]
    assert [t.error_code for t in ep.tool_calls[:3]] == ["INVALID_ARGUMENT"] * 3


def test_budget_exhausted_when_model_loops(
    tenant: Tenant, cases: list[Case], config: AgentConfig
) -> None:
    case = first(cases, "invoice_explain")
    llm = ScriptedLLM(lambda r: call("search_kb", query="invoice"))
    ep = run_episode(case, tenant, config.model_copy(update={"max_steps": 4}), llm, trial=0)
    assert ep.outcome == TurnOutcome.BUDGET_EXHAUSTED
    assert ep.steps == 4
    assert [c for c in ep.changes if c.collection != "tickets"] == []


def test_text_without_terminal_tool_gets_one_nudge(
    tenant: Tenant, cases: list[Case], config: AgentConfig
) -> None:
    case = first(cases, "payment_failed_help")
    llm = script(
        [
            lambda r: "Here is my answer without a tool.",
            lambda r: call("reply_to_customer", ticket_id=case.ticket.ticket_id, message="answer"),
        ]
    )
    ep = run_episode(case, tenant, config, llm, trial=0)
    assert ep.outcome == TurnOutcome.REPLY
    assert any("must finish" in m.content for m in ep.transcript if m.role == "user")


def test_clarify_then_user_reply_continues(
    tenant: Tenant, cases: list[Case], config: AgentConfig
) -> None:
    case = first(cases, "refund_needs_invoice")
    inv = case.hidden_facts["invoice_id"]
    amount = case.expected.changes[0].match["amount_cents"]
    llm = script(
        [
            lambda r: call(
                "ask_clarifying_question",
                ticket_id=case.ticket.ticket_id,
                question="Which invoice would you like refunded?",
            ),
            lambda r: call("issue_refund", invoice_id=inv, amount_cents=amount, reason="asked"),
            lambda r: call("reply_to_customer", ticket_id=case.ticket.ticket_id, message="done"),
        ]
    )
    ep = run_episode(case, tenant, config, llm, trial=0)
    assert ep.turns == 2
    assert ep.outcome == TurnOutcome.REPLY
    assert any(inv in m.content for m in ep.transcript if m.role == "user")
    assert ep.clarified_before_action


def test_clarify_without_user_answer_ends_episode(
    tenant: Tenant, cases: list[Case], config: AgentConfig
) -> None:
    case = first(cases, "payment_failed_help")
    llm = ScriptedLLM(
        lambda r: call("ask_clarifying_question", ticket_id=case.ticket.ticket_id, question="Hmm.")
    )
    ep = run_episode(case, tenant, config, llm, trial=0)
    assert ep.outcome == TurnOutcome.CLARIFY and ep.turns == 1


def test_unknown_requester_does_not_crash(
    tenant: Tenant, cases: list[Case], config: AgentConfig
) -> None:
    case = first(cases, "unknown_requester")
    seen: list[list[dict]] = []

    def finish(r):  # type: ignore[no-untyped-def]
        seen.append(tool_results(r))
        return call(
            "reply_to_customer",
            ticket_id=case.ticket.ticket_id,
            message="Please write from the email registered on your account.",
        )

    llm = script([lambda r: call("lookup_customer", email=case.ticket.requester_email), finish])
    ep = run_episode(case, tenant, config, llm, trial=0)
    assert ep.outcome == TurnOutcome.REPLY
    assert seen[0][0]["error"]["code"] == "NOT_FOUND"


def test_policy_violation_recorded_in_observe_mode(
    tenant: Tenant, cases: list[Case], config: AgentConfig
) -> None:
    case = first(cases, "refund_outside_window")
    inv = case.hidden_facts["invoice_id"]
    llm = script(
        [
            lambda r: call("issue_refund", invoice_id=inv, amount_cents=100, reason="x"),
            lambda r: call("reply_to_customer", ticket_id=case.ticket.ticket_id, message="done"),
        ]
    )
    ep = run_episode(case, tenant, config, llm, trial=0)
    assert "refund.outside_window" in {v.rule for v in ep.violations}


def test_enforce_mode_blocks_violation(
    tenant: Tenant, cases: list[Case], config: AgentConfig
) -> None:
    case = first(cases, "refund_outside_window")
    inv = case.hidden_facts["invoice_id"]
    llm = script(
        [
            lambda r: call("issue_refund", invoice_id=inv, amount_cents=100, reason="x"),
            lambda r: call("reply_to_customer", ticket_id=case.ticket.ticket_id, message="no"),
        ]
    )
    cfg = config.model_copy(update={"policy_guardrail": "enforce"})
    ep = run_episode(case, tenant, cfg, llm, trial=0)
    assert ep.violations == ()
    assert "refund.outside_window" in {v.rule for v in ep.blocked}
    assert [c for c in ep.changes if c.collection == "refunds"] == []


def test_injected_faults_reported_and_retried(
    tenant: Tenant, cases: list[Case], config: AgentConfig
) -> None:
    case = first(cases, "refund_eligible")
    faults = (FaultRule(op="lookup_customer", kind="error_5xx", times=1),)
    ep = run_episode(case, tenant, config, refund_script(case), trial=0, faults=faults)
    assert ep.faults_injected == (("lookup_customer", "error_5xx"),)
    assert ep.tool_calls[0].ok and ep.tool_calls[0].attempts == 2


def test_tool_results_are_json(tenant: Tenant, cases: list[Case], config: AgentConfig) -> None:
    case = first(cases, "refund_eligible")
    ep = run_episode(case, tenant, config, refund_script(case), trial=0)
    tool_messages = [m for m in ep.transcript if m.role == "tool"]
    assert tool_messages
    for m in tool_messages:
        assert isinstance(json.loads(m.content), dict)


def test_trials_use_distinct_seeds(tenant: Tenant, cases: list[Case], config: AgentConfig) -> None:
    case = first(cases, "payment_failed_help")
    seeds: list[int | None] = []

    def responder(r):  # type: ignore[no-untyped-def]
        seeds.append(r.seed)
        return call("reply_to_customer", ticket_id=case.ticket.ticket_id, message="x")

    run_episode(case, tenant, config, ScriptedLLM(responder), trial=0)
    run_episode(case, tenant, config, ScriptedLLM(responder), trial=1)
    assert seeds[0] != seeds[1]


def test_oracle_context_gives_only_gold_sections(
    tenant: Tenant, cases: list[Case], config: AgentConfig
) -> None:
    case = first(cases, "payment_failed_help")
    cfg = config.model_copy(update={"oracle_context": True})
    llm = ScriptedLLM(
        lambda r: call("reply_to_customer", ticket_id=case.ticket.ticket_id, message="x")
    )
    ep = run_episode(case, tenant, cfg, llm, trial=0)
    assert {c.section_key for c in ep.retrieved} == set(case.expected.gold_sections)
    assert all(not c.stale for c in ep.retrieved)


def test_config_hash_follows_model_copy(config: AgentConfig) -> None:
    original = config.content_hash  # computed before the copy, as in real use
    changed = config.model_copy(update={"max_steps": 3})
    assert config.content_hash == original
    assert changed.content_hash != config.content_hash
