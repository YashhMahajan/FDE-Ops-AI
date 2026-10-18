import re

from fdeops.agent.config import AgentConfig, ModelRef
from fdeops.agent.episode import ToolBox, run_external_episode
from fdeops.agent.support_agent import TurnOutcome
from fdeops.core.provenance import Provenance
from fdeops.eval.runner import run_eval
from fdeops.tenancy.loader import Tenant
from fdeops.world.cases import Case

from .conftest import first

CFG = AgentConfig(id="external", model=ModelRef(provider="external", name="naive-refunder"))


def naive_refunder(box: ToolBox) -> None:
    """Refunds the invoice in the ticket. It does not read the policy."""
    tid = box.ticket.ticket_id
    found = box.call("lookup_customer", email=box.ticket.requester_email)
    if "error" in found:
        box.call("reply_to_customer", ticket_id=tid, message="Please use your account email.")
        return
    ids = re.findall(r"inv_\w+", box.ticket.body + " ".join(box.customer_replies))
    if not ids:
        box.call("ask_clarifying_question", ticket_id=tid, question="Which invoice?")
        return
    inv = box.call("get_invoice", invoice_id=ids[-1])["data"]["invoice"]
    box.call(
        "issue_refund",
        invoice_id=inv["id"],
        amount_cents=inv["amount_cents"],
        reason="customer request",
    )
    box.call(
        "reply_to_customer", ticket_id=tid, message=f"Refunded ${inv['amount_cents'] / 100:.2f}."
    )


def broken_agent(box: ToolBox) -> None:
    raise RuntimeError("model endpoint down")


def test_external_agent_uses_the_full_connector_stack(tenant: Tenant, cases: list[Case]) -> None:
    case = first(cases, "refund_outside_window")
    ep = run_external_episode(case, tenant, CFG, naive_refunder, trial=0)
    assert ep.outcome == TurnOutcome.REPLY
    assert "refund.outside_window" in {v.rule for v in ep.violations}
    assert [t.op for t in ep.tool_calls] == [
        "lookup_customer",
        "get_invoice",
        "issue_refund",
        "reply_to_customer",
    ]
    assert ep.audit_ok and ep.trace.spans


def test_external_agent_gets_customer_reply_after_clarifying(
    tenant: Tenant, cases: list[Case]
) -> None:
    case = first(cases, "refund_needs_invoice")
    ep = run_external_episode(case, tenant, CFG, naive_refunder, trial=0)
    assert ep.turns == 2 and ep.clarified_before_action


def test_external_agent_exception_is_recorded_not_raised(tenant: Tenant, cases: list[Case]) -> None:
    ep = run_external_episode(first(cases, "invoice_explain"), tenant, CFG, broken_agent, trial=0)
    assert ep.outcome == TurnOutcome.MODEL_ERROR and "model endpoint down" in (ep.error or "")


def test_toolbox_lists_tools_in_openai_format(tenant: Tenant, cases: list[Case]) -> None:
    seen: list[list[dict]] = []

    def agent(box: ToolBox) -> None:
        seen.append(box.tools())
        box.call("escalate_to_human", ticket_id=box.ticket.ticket_id, reason_code="other", note="x")

    run_external_episode(first(cases, "invoice_explain"), tenant, CFG, agent, trial=0)
    names = {t["function"]["name"] for t in seen[0]}
    assert {"search_kb", "issue_refund", "reply_to_customer"} <= names


def test_run_eval_with_external_agent(tenant: Tenant) -> None:
    ds = tenant.build_datasets("support-core")["dev"]
    refunds = ds.model_copy(
        update={
            "cases": tuple(
                c for c in ds.cases if c.scenario in ("refund_eligible", "refund_outside_window")
            )
        }
    )
    run = run_eval(tenant, CFG, refunds, None, external_agent=naive_refunder)
    assert run.provenance == Provenance.MEASURED_IN_SIMULATION
    assert run.llm_provider == "external:naive_refunder"
    outside = [r for r in run.results if r.scenario == "refund_outside_window"]
    assert outside and not any(r.success for r in outside)
