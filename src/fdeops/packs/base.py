"""The contract every domain pack fulfils."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol

from fdeops.connectors.base import Connector
from fdeops.core.model import FrozenModel
from fdeops.llm.types import LLMClient
from fdeops.world.cases import TicketInput
from fdeops.world.policy import Violation
from fdeops.world.scenario import Scenario
from fdeops.world.state import StateChange, WorldState
from fdeops.world.user_sim import UserSimulator


class PolicyChecker(Protocol):
    def check(
        self, op: str, args: dict[str, Any], state: Any, requester_email: str, now: datetime
    ) -> list[Violation]: ...


class DomainPack(Protocol):
    id: str
    generator_version: str
    policy_model: type[FrozenModel]
    world_spec_model: type[FrozenModel]
    agent_scopes: frozenset[str]
    references: dict[str, dict[str, str]]
    """collection -> {field: referenced collection}. The ingest step checks these references."""
    normalizers: dict[str, Any]
    """collection -> function that cleans one raw record (for example, email case)."""
    knowledge_rules: dict[str, tuple[str, ...]]
    """KB section key -> the policy rules that the section controls. Diagnosis uses it to link a
    violation to stale knowledge."""

    def generate_world(self, spec: Any, now: datetime) -> WorldState: ...

    def scenarios(self) -> dict[str, Scenario]: ...

    def build_connectors(self, state: Any) -> list[Connector]: ...

    def policy_engine(self, policy: Any) -> PolicyChecker: ...

    def user_simulator(self) -> UserSimulator: ...

    def is_outcome_change(self, change: StateChange) -> bool:
        """Whether a state change is a business outcome the grader compares against the oracle."""
        ...

    def open_ticket(self, state: Any, ticket: TicketInput, now: datetime) -> None: ...

    def add_customer_reply(
        self, state: Any, ticket_id: str, message: str, now: datetime
    ) -> None: ...

    def heuristic_model(
        self, seed: int = 0, error_rates: Mapping[str, float] | None = None
    ) -> LLMClient:
        """A rule-based stand-in model for pipeline tests (outputs labeled pipeline-test)."""
        ...

    def agent_messages(self, state: Any, ticket_id: str) -> list[str]:
        """Everything the agent said to the customer on this ticket, in order."""
        ...
