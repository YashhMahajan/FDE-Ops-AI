from datetime import timedelta

from fdeops.packs.billing.entities import Customer, Invoice, User
from fdeops.packs.billing.policy import BillingPolicy, BillingPolicyEngine
from fdeops.packs.billing.state import BillingState

from .conftest import NOW


def invoice(days_ago: int, amount: int = 9900, status: str = "paid") -> Invoice:
    paid = NOW - timedelta(days=days_ago)
    return Invoice(
        id="inv_p",
        customer_id="cus_p",
        amount_cents=amount,
        period_start=paid.date(),
        period_end=(paid + timedelta(days=30)).date(),
        issued_at=paid,
        paid_at=paid,
        status=status,
    )  # type: ignore[arg-type]


def test_window_boundary_inclusive(policy: BillingPolicy) -> None:
    eng = BillingPolicyEngine(policy)
    assert eng.refund_decision(invoice(14), NOW).outcome == "refund"
    assert eng.refund_decision(invoice(15), NOW).outcome == "decline_window"


def test_over_limit_escalates(policy: BillingPolicy) -> None:
    eng = BillingPolicyEngine(policy)
    assert eng.refund_decision(invoice(1, amount=20001), NOW).outcome == "escalate_over_limit"
    d = eng.refund_decision(invoice(1, amount=20000), NOW)
    assert d.outcome == "refund" and d.amount_cents == 20000


def test_outside_window_wins_over_limit(policy: BillingPolicy) -> None:
    eng = BillingPolicyEngine(policy)
    assert eng.refund_decision(invoice(40, amount=90000), NOW).outcome == "decline_window"


def test_unpaid_invoice_declined(policy: BillingPolicy) -> None:
    eng = BillingPolicyEngine(policy)
    assert eng.refund_decision(invoice(1, status="failed"), NOW).outcome == "decline_status"


def _state() -> BillingState:
    s = BillingState()
    s.upsert(
        "customers",
        Customer(
            id="cus_p",
            company="P",
            plan_id="plan_growth",
            status="active",
            created_at=NOW - timedelta(days=100),
        ),
    )
    s.upsert(
        "customers",
        Customer(
            id="cus_q",
            company="Q",
            plan_id="plan_growth",
            status="active",
            created_at=NOW - timedelta(days=100),
        ),
    )
    s.upsert(
        "users", User(id="u1", customer_id="cus_p", email="o@p.example", name="O", role="owner")
    )
    s.upsert(
        "users", User(id="u2", customer_id="cus_p", email="m@p.example", name="M", role="member")
    )
    s.upsert(
        "users", User(id="u3", customer_id="cus_q", email="o@q.example", name="Q", role="owner")
    )
    return s


def test_check_clean_refund_has_no_violations(policy: BillingPolicy) -> None:
    s = _state()
    s.upsert("invoices", invoice(3))
    v = BillingPolicyEngine(policy).check(
        "issue_refund", {"invoice_id": "inv_p", "amount_cents": 9900}, s, "o@p.example", NOW
    )
    assert v == []


def test_check_flags_wrong_customer(policy: BillingPolicy) -> None:
    s = _state()
    s.upsert("invoices", invoice(3))
    v = BillingPolicyEngine(policy).check(
        "issue_refund", {"invoice_id": "inv_p", "amount_cents": 9900}, s, "o@q.example", NOW
    )
    assert [x.rule for x in v] == ["refund.wrong_customer"]
    assert v[0].severity == "critical"


def test_check_flags_outside_window_and_over_limit(policy: BillingPolicy) -> None:
    s = _state()
    s.upsert("invoices", invoice(20))
    v = BillingPolicyEngine(policy).check(
        "issue_refund", {"invoice_id": "inv_p", "amount_cents": 9900}, s, "o@p.example", NOW
    )
    assert "refund.outside_window" in {x.rule for x in v}
    s.upsert("invoices", invoice(2, amount=50000))
    v2 = BillingPolicyEngine(policy).check(
        "issue_refund", {"invoice_id": "inv_p", "amount_cents": 50000}, s, "o@p.example", NOW
    )
    assert "refund.over_auto_limit" in {x.rule for x in v2}


def test_export_member_role_violation(policy: BillingPolicy) -> None:
    s = _state()
    v = BillingPolicyEngine(policy).check(
        "request_data_export",
        {"customer_id": "cus_p", "requester_email": "m@p.example"},
        s,
        "m@p.example",
        NOW,
    )
    assert [x.rule for x in v] == ["export.unauthorized_role"]


def test_plan_change_other_customer(policy: BillingPolicy) -> None:
    s = _state()
    v = BillingPolicyEngine(policy).check(
        "change_plan", {"customer_id": "cus_q", "plan_id": "plan_starter"}, s, "o@p.example", NOW
    )
    assert [x.rule for x in v] == ["plan.wrong_customer"]


def test_read_ops_never_violate(policy: BillingPolicy) -> None:
    assert (
        BillingPolicyEngine(policy).check(
            "get_invoice", {"invoice_id": "x"}, _state(), "o@p.example", NOW
        )
        == []
    )
