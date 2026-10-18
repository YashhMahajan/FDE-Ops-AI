"""Account, shipment and claim APIs over a ``LogisticsState``.

As in the billing pack, the APIs keep the data correct (no claim above the declared value, no
address change after delivery) but do not apply the business policy (claim windows, limits, the
statuses that permit an address change). The agent must obey the policy, and the policy monitor
checks it.
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
from fdeops.packs.common.schema import ID, TEXT, not_found, obj, spec
from fdeops.packs.common.tickets import build_ticketing_connector
from fdeops.packs.logistics.entities import AddressChange, Claim
from fdeops.packs.logistics.state import LogisticsState

AGENT_SCOPES = frozenset(
    {
        "accounts:read",
        "shipments:read",
        "shipments:write",
        "claims:write",
        "tickets:write",
        "tickets:escalate",
        "kb:read",
    }
)


def _shipment_view(s: Any) -> dict[str, Any]:
    data: dict[str, Any] = s.model_dump(mode="json")
    return data


def build_logistics_connectors(state: LogisticsState) -> list[InProcessConnector]:
    def lookup_customer(args: dict[str, Any], ctx: OpContext) -> Any:
        user = state.user_by_email(args["email"])
        if user is None:
            raise not_found("user with that email")
        return {
            "user": user.model_dump(mode="json"),
            "account": state.accounts[user.account_id].model_dump(mode="json"),
        }

    def list_shipments(args: dict[str, Any], ctx: OpContext) -> Any:
        if args["account_id"] not in state.accounts:
            raise not_found("account")
        items = sorted(
            (s for s in state.shipments.values() if s.account_id == args["account_id"]),
            key=lambda s: s.shipped_at,
            reverse=True,
        )
        return {"shipments": [_shipment_view(s) for s in items]}

    def track_shipment(args: dict[str, Any], ctx: OpContext) -> Any:
        s = state.shipment_by_tracking(args["tracking_number"])
        if s is None:
            raise not_found("shipment with that tracking number")
        return {"shipment": _shipment_view(s)}

    def update_delivery_address(args: dict[str, Any], ctx: OpContext) -> Any:
        s = state.shipments.get(args["shipment_id"])
        if s is None:
            raise not_found("shipment")
        if s.status in ("delivered", "lost"):
            raise OpFailure.of(ErrorCode.CONFLICT, f"the shipment is {s.status}")
        change = AddressChange(
            id=stable_id("adr", s.id, args["new_address"]),
            shipment_id=s.id,
            new_address=args["new_address"],
            created_at=ctx.clock.now(),
        )
        state.upsert("address_changes", change)
        state.upsert("shipments", s.model_copy(update={"destination_address": args["new_address"]}))
        return {"address_change": change.model_dump(mode="json")}

    def file_claim(args: dict[str, Any], ctx: OpContext) -> Any:
        key = args.get("idempotency_key") or ctx.idempotency_key
        if key:
            for c in state.claims.values():
                if c.idempotency_key == key:
                    return {"claim": c.model_dump(mode="json"), "duplicate": True}
        s = state.shipments.get(args["shipment_id"])
        if s is None:
            raise not_found("shipment")
        amount = int(args["amount_cents"])
        if amount > s.declared_value_cents:
            raise OpFailure.of(
                ErrorCode.CONFLICT,
                f"the amount is more than the declared value {s.declared_value_cents}",
            )
        n = sum(1 for c in state.claims.values() if c.shipment_id == s.id)
        claim = Claim(
            id=stable_id("clm", s.id, key or n),
            shipment_id=s.id,
            kind=args["kind"],
            amount_cents=amount,
            description=args["description"],
            status="approved",
            created_at=ctx.clock.now(),
            idempotency_key=key,
        )
        state.upsert("claims", claim)
        return {"claim": claim.model_dump(mode="json"), "duplicate": False}

    accounts: dict[str, tuple[OpSpec, Handler]] = {
        "lookup_customer": (
            spec(
                "lookup_customer",
                "Find the user and the account for an email address.",
                obj({"email": ID}, ["email"]),
                "accounts:read",
            ),
            lookup_customer,
        ),
    }
    shipments: dict[str, tuple[OpSpec, Handler]] = {
        "list_shipments": (
            spec(
                "list_shipments",
                "List the shipments of an account, newest first.",
                obj({"account_id": ID}, ["account_id"]),
                "shipments:read",
            ),
            list_shipments,
        ),
        "track_shipment": (
            spec(
                "track_shipment",
                "Get the status of a shipment from its tracking number.",
                obj({"tracking_number": ID}, ["tracking_number"]),
                "shipments:read",
            ),
            track_shipment,
        ),
        "update_delivery_address": (
            spec(
                "update_delivery_address",
                "Change the delivery address of a shipment.",
                obj({"shipment_id": ID, "new_address": TEXT}, ["shipment_id", "new_address"]),
                "shipments:write",
                mutating=True,
            ),
            update_delivery_address,
        ),
    }
    claims: dict[str, tuple[OpSpec, Handler]] = {
        "file_claim": (
            spec(
                "file_claim",
                "Open and approve a damage or loss claim. The amount is in cents.",
                obj(
                    {
                        "shipment_id": ID,
                        "kind": {"type": "string", "enum": ["damage", "loss"]},
                        "amount_cents": {"type": "integer", "minimum": 1},
                        "description": TEXT,
                        "idempotency_key": {"type": "string"},
                    },
                    ["shipment_id", "kind", "amount_cents", "description"],
                ),
                "claims:write",
                mutating=True,
            ),
            file_claim,
        ),
    }
    return [
        InProcessConnector("accounts", accounts),
        InProcessConnector("shipments", shipments),
        InProcessConnector("claims", claims),
        build_ticketing_connector(state),
    ]
