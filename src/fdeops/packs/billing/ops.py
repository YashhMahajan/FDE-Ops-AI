"""Billing, accounts and ticketing APIs over a ``BillingState``.

The APIs enforce *data invariants* (an invoice can't be refunded beyond its amount) but not
*business policy* (refund windows, limits). Following policy is the agent's job; checking it is the
policy monitor's. That separation mirrors real systems, where the payments API happily refunds
whatever an authorized caller asks for.
"""

from typing import Any

from fdeops.connectors.base import (
    ErrorCode,
    Handler,
    InProcessConnector,
    OpContext,
    OpFailure,
    OpSpec,
)
from fdeops.core.ids import stable_id
from fdeops.packs.billing.entities import ExportRequest, Refund
from fdeops.packs.billing.state import BillingState
from fdeops.packs.common.tickets import build_ticketing_connector

AGENT_SCOPES = frozenset(
    {
        "accounts:read",
        "billing:read",
        "billing:refund",
        "billing:write",
        "data:export",
        "tickets:write",
        "tickets:escalate",
        "kb:read",
    }
)


def _obj(props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


_ID = {"type": "string", "minLength": 1}
_TEXT = {"type": "string", "minLength": 1, "maxLength": 4000}


def _spec(
    name: str,
    desc: str,
    params: dict[str, Any],
    scope: str,
    mutating: bool = False,
    terminal: str | None = None,
) -> OpSpec:
    return OpSpec(
        name=name,
        description=desc,
        parameters=params,
        required_scope=scope,
        mutating=mutating,
        terminal=terminal,
    )


def _not_found(what: str) -> OpFailure:
    return OpFailure.of(ErrorCode.NOT_FOUND, f"{what} not found")


def build_billing_connectors(state: BillingState) -> list[InProcessConnector]:
    def lookup_customer(args: dict[str, Any], ctx: OpContext) -> Any:
        user = state.user_by_email(args["email"])
        if user is None:
            raise _not_found("user with that email")
        customer = state.customers[user.customer_id]
        plan = state.plans.get(customer.plan_id)
        return {
            "user": user.model_dump(mode="json"),
            "customer": customer.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json") if plan else None,
        }

    def list_invoices(args: dict[str, Any], ctx: OpContext) -> Any:
        if args["customer_id"] not in state.customers:
            raise _not_found("customer")
        invs = [i for i in state.invoices.values() if i.customer_id == args["customer_id"]]
        invs.sort(key=lambda i: i.issued_at, reverse=True)
        return {"invoices": [i.model_dump(mode="json") for i in invs]}

    def get_invoice(args: dict[str, Any], ctx: OpContext) -> Any:
        inv = state.invoices.get(args["invoice_id"])
        if inv is None:
            raise _not_found("invoice")
        return {"invoice": inv.model_dump(mode="json")}

    def issue_refund(args: dict[str, Any], ctx: OpContext) -> Any:
        key = args.get("idempotency_key") or ctx.idempotency_key
        if key:
            for r in state.refunds.values():
                if r.idempotency_key == key:
                    return {"refund": r.model_dump(mode="json"), "duplicate": True}
        inv = state.invoices.get(args["invoice_id"])
        if inv is None:
            raise _not_found("invoice")
        if inv.status not in ("paid", "partially_refunded"):
            raise OpFailure.of(ErrorCode.CONFLICT, f"invoice status {inv.status} is not refundable")
        amount = int(args["amount_cents"])
        if amount > inv.refundable_cents:
            raise OpFailure.of(
                ErrorCode.CONFLICT, f"amount exceeds refundable balance {inv.refundable_cents}"
            )
        n = sum(1 for r in state.refunds.values() if r.invoice_id == inv.id)
        refund = Refund(
            id=stable_id("ref", inv.id, key or n),
            invoice_id=inv.id,
            amount_cents=amount,
            reason=args["reason"],
            created_at=ctx.clock.now(),
            idempotency_key=key,
        )
        state.upsert("refunds", refund)
        refunded = inv.refunded_cents + amount
        state.upsert(
            "invoices",
            inv.model_copy(
                update={
                    "refunded_cents": refunded,
                    "status": "refunded" if refunded == inv.amount_cents else "partially_refunded",
                }
            ),
        )
        return {"refund": refund.model_dump(mode="json"), "duplicate": False}

    def change_plan(args: dict[str, Any], ctx: OpContext) -> Any:
        customer = state.customers.get(args["customer_id"])
        if customer is None:
            raise _not_found("customer")
        if args["plan_id"] not in state.plans:
            raise _not_found("plan")
        if customer.plan_id == args["plan_id"]:
            raise OpFailure.of(ErrorCode.CONFLICT, "customer is already on that plan")
        state.upsert("customers", customer.model_copy(update={"plan_id": args["plan_id"]}))
        return {
            "customer_id": customer.id,
            "previous_plan_id": customer.plan_id,
            "plan_id": args["plan_id"],
        }

    def request_data_export(args: dict[str, Any], ctx: OpContext) -> Any:
        if args["customer_id"] not in state.customers:
            raise _not_found("customer")
        n = len(state.export_requests)
        req = ExportRequest(
            id=stable_id("exp", args["customer_id"], n),
            customer_id=args["customer_id"],
            requested_by=args["requester_email"],
            created_at=ctx.clock.now(),
        )
        state.upsert("export_requests", req)
        return {"export_request": req.model_dump(mode="json")}

    accounts: dict[str, tuple[OpSpec, Handler]] = {
        "lookup_customer": (
            _spec(
                "lookup_customer",
                "Find the user, customer account and plan for an email address.",
                _obj({"email": _ID}, ["email"]),
                "accounts:read",
            ),
            lookup_customer,
        ),
    }
    billing: dict[str, tuple[OpSpec, Handler]] = {
        "list_invoices": (
            _spec(
                "list_invoices",
                "List a customer's invoices, newest first.",
                _obj({"customer_id": _ID}, ["customer_id"]),
                "billing:read",
            ),
            list_invoices,
        ),
        "get_invoice": (
            _spec(
                "get_invoice",
                "Get one invoice by id.",
                _obj({"invoice_id": _ID}, ["invoice_id"]),
                "billing:read",
            ),
            get_invoice,
        ),
        "issue_refund": (
            _spec(
                "issue_refund",
                "Refund part or all of a paid invoice. Amount is in cents.",
                _obj(
                    {
                        "invoice_id": _ID,
                        "amount_cents": {"type": "integer", "minimum": 1},
                        "reason": _TEXT,
                        "idempotency_key": {"type": "string"},
                    },
                    ["invoice_id", "amount_cents", "reason"],
                ),
                "billing:refund",
                mutating=True,
            ),
            issue_refund,
        ),
        "change_plan": (
            _spec(
                "change_plan",
                "Move a customer to a different plan.",
                _obj({"customer_id": _ID, "plan_id": _ID}, ["customer_id", "plan_id"]),
                "billing:write",
                mutating=True,
            ),
            change_plan,
        ),
        "request_data_export": (
            _spec(
                "request_data_export",
                "Start a full data export for a customer account.",
                _obj(
                    {"customer_id": _ID, "requester_email": _ID}, ["customer_id", "requester_email"]
                ),
                "data:export",
                mutating=True,
            ),
            request_data_export,
        ),
    }
    return [
        InProcessConnector("accounts", accounts),
        InProcessConnector("billing", billing),
        build_ticketing_connector(state),
    ]
