from typing import Protocol

from fdeops.world.cases import Case


class UserSimulator(Protocol):
    """Plays the customer when the agent asks a clarifying question. ``None`` means no reply."""

    def respond(self, case: Case, agent_message: str) -> str | None: ...
