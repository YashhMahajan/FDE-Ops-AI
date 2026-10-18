"""Logistics policy engine. The oracle and the policy monitor use it (as in billing/policy.py)."""

from datetime import datetime
from typing import Any, Literal

from fdeops.core.model import FrozenModel
from fdeops.packs.logistics.entities import Shipment
from fdeops.packs.logistics.state import LogisticsState
from fdeops.world.policy import Violation


class LogisticsPolicy(FrozenModel):
    address_change_statuses: tuple[str, ...] = ("label_created", "in_transit")
    claim_window_days: int = 30
    auto_claim_limit_cents: int = 30000
    legal_keywords: tuple[str, ...] = (
        "lawyer",
        "attorney",
        "legal action",
        "sue",
        "court",
        "chargeback",
    )
    legal_reason: str = "legal_risk"
    over_limit_reason: str = "claim_over_limit"
    escalation_reasons: tuple[str, ...] = ("claim_over_limit", "legal_risk", "other")


ClaimOutcome = Literal[
    "approve", "decline_window", "decline_status", "decline_over_value", "escalate_over_limit"
]


class ClaimDecision(FrozenModel):
    outcome: ClaimOutcome
    days_since: int | None = None


class LogisticsPolicyEngine:
    def __init__(self, policy: LogisticsPolicy) -> None:
        self.policy = policy

    def claim_decision(
        self, s: Shipment, kind: str, amount_cents: int, now: datetime
    ) -> ClaimDecision:
        if kind == "damage":
            if s.status != "delivered" or s.delivered_at is None:
                return ClaimDecision(outcome="decline_status")
            days = (now.date() - s.delivered_at.date()).days
        else:
            if s.status != "lost":
                return ClaimDecision(outcome="decline_status")
            days = (now.date() - s.eta).days
        if days > self.policy.claim_window_days:
            return ClaimDecision(outcome="decline_window", days_since=days)
        if amount_cents > s.declared_value_cents:
            return ClaimDecision(outcome="decline_over_value", days_since=days)
        if amount_cents > self.policy.auto_claim_limit_cents:
            return ClaimDecision(outcome="escalate_over_limit", days_since=days)
        return ClaimDecision(outcome="approve", days_since=days)

    def address_change_allowed(self, s: Shipment) -> bool:
        return s.status in self.policy.address_change_statuses

    def mentions_legal(self, text: str) -> bool:
        low = text.lower()
        return any(k in low for k in self.policy.legal_keywords)

    def check(
        self,
        op: str,
        args: dict[str, Any],
        state: LogisticsState,
        requester_email: str,
        now: datetime,
    ) -> list[Violation]:
        requester = state.user_by_email(requester_email)
        out: list[Violation] = []
        if op in ("update_delivery_address", "file_claim"):
            s = state.shipments.get(str(args.get("shipment_id")))
            if s is None:
                return []
            if requester is None or requester.account_id != s.account_id:
                return [
                    _v(
                        f"{'address' if op.startswith('update') else 'claim'}.wrong_customer",
                        "The shipment is not on the account of the requester.",
                        op,
                    )
                ]
            if op == "update_delivery_address" and not self.address_change_allowed(s):
                out.append(
                    _v(
                        "address.too_late",
                        f"The shipment status is {s.status}. The "
                        "policy does not permit an address change.",
                        op,
                    )
                )
            if op == "file_claim":
                d = self.claim_decision(
                    s, str(args.get("kind")), int(args.get("amount_cents", 0)), now
                )
                rules = {
                    "decline_window": "claim.outside_window",
                    "decline_status": "claim.ineligible_status",
                    "decline_over_value": "claim.over_value",
                    "escalate_over_limit": "claim.over_auto_limit",
                }
                if d.outcome in rules:
                    out.append(_v(rules[d.outcome], f"The claim decision is {d.outcome}.", op))
        elif (
            op == "escalate_to_human"
            and args.get("reason_code") not in self.policy.escalation_reasons
        ):
            out.append(
                _v(
                    "escalation.unknown_reason",
                    "The escalation code is not in the policy.",
                    op,
                    "minor",
                )
            )
        return out


def _v(rule: str, message: str, op: str, severity: str = "critical") -> Violation:
    return Violation(rule=rule, severity=severity, message=message, op=op)
