from collections.abc import Mapping
from datetime import datetime
from typing import Any

from fdeops.connectors.base import Connector
from fdeops.core.model import FrozenModel
from fdeops.packs.billing.entities import Reply, Ticket
from fdeops.packs.billing.generator import BillingWorldSpec, generate_base_world
from fdeops.packs.billing.heuristic import BillingHeuristicLLM
from fdeops.packs.billing.ops import AGENT_SCOPES, build_billing_connectors
from fdeops.packs.billing.policy import BillingPolicy, BillingPolicyEngine
from fdeops.packs.billing.scenarios import SCENARIOS
from fdeops.packs.billing.state import BillingState
from fdeops.packs.billing.user_sim import BillingUserSimulator
from fdeops.world.cases import TicketInput
from fdeops.world.scenario import Scenario
from fdeops.world.state import StateChange


class BillingPack:
    id = "billing"
    generator_version = "billing-1"
    # Annotated with the protocol's types: protocol attributes are invariant.
    policy_model: type[FrozenModel] = BillingPolicy
    world_spec_model: type[FrozenModel] = BillingWorldSpec
    agent_scopes = AGENT_SCOPES
    knowledge_rules: dict[str, tuple[str, ...]] = {
        "refund-policy#refund-window": ("refund.outside_window",),
        "refund-policy#large-refunds": ("refund.over_auto_limit",),
        "data-export#who-can-request": ("export.unauthorized_role",),
        "plans#changing-plans": ("plan.unauthorized_role",),
    }

    def generate_world(self, spec: BillingWorldSpec, now: datetime) -> BillingState:
        return generate_base_world(spec, now)

    def scenarios(self) -> dict[str, Scenario]:
        return dict(SCENARIOS)

    def build_connectors(self, state: BillingState) -> list[Connector]:
        return list(build_billing_connectors(state))

    def policy_engine(self, policy: BillingPolicy) -> BillingPolicyEngine:
        return BillingPolicyEngine(policy)

    def user_simulator(self) -> BillingUserSimulator:
        return BillingUserSimulator()

    def is_outcome_change(self, change: StateChange) -> bool:
        if change.collection in ("refunds", "export_requests"):
            return True
        if change.collection == "customers":
            return "plan_id" in change.changed_fields
        if change.collection == "tickets":
            return "escalation" in change.changed_fields
        return False

    def open_ticket(self, state: BillingState, ticket: TicketInput, now: datetime) -> None:
        state.upsert(
            "tickets",
            Ticket(
                id=ticket.ticket_id,
                customer_id=None,
                requester_email=ticket.requester_email,
                subject=ticket.subject,
                body=ticket.body,
                status="open",
                created_at=now,
            ),
        )

    def add_customer_reply(
        self, state: BillingState, ticket_id: str, message: str, now: datetime
    ) -> None:
        t = state.tickets[ticket_id]
        reply = Reply(author="customer", message=message, at=now)
        state.upsert(
            "tickets", t.model_copy(update={"replies": (*t.replies, reply), "status": "open"})
        )

    def agent_messages(self, state: BillingState, ticket_id: str) -> list[str]:
        t = state.tickets.get(ticket_id)
        # Customer-facing only: escalation notes are internal and are not shown to the customer.
        return [r.message for r in t.replies if r.author == "agent"] if t else []

    def heuristic_model(
        self, seed: int = 0, error_rates: Mapping[str, float] | None = None
    ) -> BillingHeuristicLLM:
        return BillingHeuristicLLM(seed=seed, error_rates=error_rates)

    def describe(self) -> dict[str, Any]:
        return {"id": self.id, "scenarios": sorted(SCENARIOS)}
