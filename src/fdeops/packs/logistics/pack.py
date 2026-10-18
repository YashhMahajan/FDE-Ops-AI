from collections.abc import Mapping
from datetime import datetime
from typing import Any

from fdeops.connectors.base import Connector
from fdeops.core.model import FrozenModel
from fdeops.packs.common import tickets
from fdeops.packs.common.normalize import normalize_email
from fdeops.packs.logistics.generator import LogisticsWorldSpec, generate_base_world
from fdeops.packs.logistics.heuristic import LogisticsHeuristicLLM
from fdeops.packs.logistics.ops import AGENT_SCOPES, build_logistics_connectors
from fdeops.packs.logistics.policy import LogisticsPolicy, LogisticsPolicyEngine
from fdeops.packs.logistics.scenarios import SCENARIOS
from fdeops.packs.logistics.state import LogisticsState
from fdeops.packs.logistics.user_sim import LogisticsUserSimulator
from fdeops.world.cases import TicketInput
from fdeops.world.scenario import Scenario
from fdeops.world.state import StateChange


class LogisticsPack:
    id = "logistics"
    generator_version = "logistics-1"
    policy_model: type[FrozenModel] = LogisticsPolicy
    world_spec_model: type[FrozenModel] = LogisticsWorldSpec
    agent_scopes = AGENT_SCOPES
    references: dict[str, dict[str, str]] = {
        "users": {"account_id": "accounts"},
        "shipments": {"account_id": "accounts"},
        "claims": {"shipment_id": "shipments"},
        "address_changes": {"shipment_id": "shipments"},
    }
    normalizers: dict[str, Any] = {"users": normalize_email}
    knowledge_rules: dict[str, tuple[str, ...]] = {
        "claims#large-claims": ("claim.over_auto_limit",),
        "claims#damage-claims": ("claim.outside_window",),
        "address-changes#when-possible": ("address.too_late",),
    }

    def generate_world(self, spec: LogisticsWorldSpec, now: datetime) -> LogisticsState:
        return generate_base_world(spec, now)

    def scenarios(self) -> dict[str, Scenario]:
        return dict(SCENARIOS)

    def build_connectors(self, state: LogisticsState) -> list[Connector]:
        return list(build_logistics_connectors(state))

    def policy_engine(self, policy: LogisticsPolicy) -> LogisticsPolicyEngine:
        return LogisticsPolicyEngine(policy)

    def user_simulator(self) -> LogisticsUserSimulator:
        return LogisticsUserSimulator()

    def is_outcome_change(self, change: StateChange) -> bool:
        if change.collection in ("claims", "address_changes"):
            return True
        if change.collection == "tickets":
            return "escalation" in change.changed_fields
        return False

    def open_ticket(self, state: LogisticsState, ticket: TicketInput, now: datetime) -> None:
        tickets.open_ticket(state, ticket, now)

    def add_customer_reply(
        self, state: LogisticsState, ticket_id: str, message: str, now: datetime
    ) -> None:
        tickets.add_customer_reply(state, ticket_id, message, now)

    def agent_messages(self, state: LogisticsState, ticket_id: str) -> list[str]:
        return tickets.agent_messages(state, ticket_id)

    def heuristic_model(
        self, seed: int = 0, error_rates: Mapping[str, float] | None = None
    ) -> LogisticsHeuristicLLM:
        return LogisticsHeuristicLLM(seed=seed, error_rates=error_rates)
