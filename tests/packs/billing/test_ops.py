from datetime import timedelta
from typing import Any

import pytest

from fdeops.connectors.base import ConnectorRegistry, ErrorCode, OpContext
from fdeops.core.clock import FakeClock
from fdeops.packs.billing.entities import Customer, Invoice, Ticket, User
from fdeops.packs.billing.ops import AGENT_SCOPES, build_billing_connectors
from fdeops.packs.billing.state import BillingState

from .conftest import NOW


@pytest.fixture
def state(world: BillingState) -> BillingState:
    s = world.copy()
    s.upsert(
        "customers",
        Customer(
            id="cus_t",
            company="Testco",
            plan_id="plan_growth",
            status="active",
            created_at=NOW - timedelta(days=200),
        ),
    )
    s.upsert(
        "users",
        User(
            id="usr_t",
            customer_id="cus_t",
            email="owner@testco.example",
            name="Tess Owner",
            role="owner",
        ),
    )
    s.upsert(
        "invoices",
        Invoice(
            id="inv_t",
            customer_id="cus_t",
            amount_cents=9900,
            period_start=(NOW - timedelta(days=5)).date(),
            period_end=(NOW + timedelta(days=25)).date(),
            issued_at=NOW - timedelta(days=5),
            paid_at=NOW - timedelta(days=5),
            status="paid",
        ),
    )
    s.upsert(
        "tickets",
        Ticket(
            id="tkt_t",
            customer_id=None,
            requester_email="owner@testco.example",
            subject="s",
            body="b",
            status="open",
            created_at=NOW,
        ),
    )
    return s


def call(state: BillingState, op: str, args: dict[str, Any], key: str | None = None):  # type: ignore[no-untyped-def]
    reg = ConnectorRegistry(build_billing_connectors(state))
    ctx = OpContext(
        tenant_id="t", actor="agent", scopes=AGENT_SCOPES, clock=FakeClock(NOW), idempotency_key=key
    )
    return reg.call(op, args, ctx)


def test_lookup_customer(state: BillingState) -> None:
    r = call(state, "lookup_customer", {"email": "OWNER@testco.example"})
    assert r.ok
    assert r.data["customer"]["id"] == "cus_t"
    assert r.data["user"]["role"] == "owner"
    assert r.data["plan"]["name"] == "Growth"


def test_lookup_unknown_email_not_found(state: BillingState) -> None:
    r = call(state, "lookup_customer", {"email": "nobody@nowhere.example"})
    assert r.error is not None and r.error.code == ErrorCode.NOT_FOUND


def test_list_invoices_newest_first(state: BillingState) -> None:
    r = call(state, "list_invoices", {"customer_id": "cus_t"})
    assert [i["id"] for i in r.data["invoices"]] == ["inv_t"]


def test_refund_full_updates_invoice(state: BillingState) -> None:
    r = call(
        state, "issue_refund", {"invoice_id": "inv_t", "amount_cents": 9900, "reason": "asked"}
    )
    assert r.ok
    assert state.invoices["inv_t"].status == "refunded"
    assert state.invoices["inv_t"].refunded_cents == 9900
    assert len([x for x in state.refunds.values() if x.invoice_id == "inv_t"]) == 1


def test_partial_refund_status(state: BillingState) -> None:
    call(state, "issue_refund", {"invoice_id": "inv_t", "amount_cents": 1000, "reason": "x"})
    assert state.invoices["inv_t"].status == "partially_refunded"


def test_refund_exceeding_remaining_conflict(state: BillingState) -> None:
    r = call(state, "issue_refund", {"invoice_id": "inv_t", "amount_cents": 9901, "reason": "x"})
    assert r.error is not None and r.error.code == ErrorCode.CONFLICT
    assert state.invoices["inv_t"].status == "paid"


def test_refund_idempotency_key_returns_same_refund(state: BillingState) -> None:
    a = call(
        state, "issue_refund", {"invoice_id": "inv_t", "amount_cents": 500, "reason": "x"}, key="k1"
    )
    b = call(
        state, "issue_refund", {"invoice_id": "inv_t", "amount_cents": 500, "reason": "x"}, key="k1"
    )
    assert a.ok and b.ok
    assert a.data["refund"]["id"] == b.data["refund"]["id"]
    assert b.data["duplicate"] is True
    assert state.invoices["inv_t"].refunded_cents == 500


def test_change_plan(state: BillingState) -> None:
    r = call(state, "change_plan", {"customer_id": "cus_t", "plan_id": "plan_starter"})
    assert r.ok and state.customers["cus_t"].plan_id == "plan_starter"
    again = call(state, "change_plan", {"customer_id": "cus_t", "plan_id": "plan_starter"})
    assert again.error is not None and again.error.code == ErrorCode.CONFLICT


def test_escalate_sets_status(state: BillingState) -> None:
    r = call(
        state,
        "escalate_to_human",
        {"ticket_id": "tkt_t", "reason_code": "refund_over_limit", "note": "big"},
    )
    assert r.ok
    t = state.tickets["tkt_t"]
    assert t.status == "escalated"
    assert t.escalation is not None and t.escalation.reason_code == "refund_over_limit"


def test_reply_and_clarify_statuses(state: BillingState) -> None:
    call(state, "ask_clarifying_question", {"ticket_id": "tkt_t", "question": "Which invoice?"})
    assert state.tickets["tkt_t"].status == "pending_customer"
    call(state, "reply_to_customer", {"ticket_id": "tkt_t", "message": "Done"})
    t = state.tickets["tkt_t"]
    assert t.status == "solved"
    assert [r.message for r in t.replies] == ["Which invoice?", "Done"]


def test_terminal_ops_marked(state: BillingState) -> None:
    reg = ConnectorRegistry(build_billing_connectors(state))
    terminals = {s.name: s.terminal for s in reg.specs() if s.terminal}
    assert terminals == {
        "reply_to_customer": "reply",
        "ask_clarifying_question": "clarify",
        "escalate_to_human": "escalate",
    }


def test_export_idempotency_key_returns_same_request(state: BillingState) -> None:
    args = {"customer_id": "cus_t", "requester_email": "owner@testco.example"}
    a = call(state, "request_data_export", args, key="exp-1")
    b = call(state, "request_data_export", args, key="exp-1")
    assert a.ok and b.ok
    assert a.data["export_request"]["id"] == b.data["export_request"]["id"]
    assert b.data["duplicate"] is True
    assert len(state.export_requests) == 1


def test_change_plan_retry_with_same_key_succeeds(state: BillingState) -> None:
    args = {"customer_id": "cus_t", "plan_id": "plan_starter"}
    assert call(state, "change_plan", args, key="pc-1").ok
    again = call(state, "change_plan", args, key="pc-1")
    assert again.ok and again.data["duplicate"] is True
    other = call(state, "change_plan", args, key="pc-2")
    assert other.error is not None and other.error.code == ErrorCode.CONFLICT
