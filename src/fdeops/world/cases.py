"""Cases and their ground truth.

Ground truth (``Expected``) is computed by a domain pack's policy oracle from world state.
It is never written by an LLM.
"""

import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from fdeops.core.model import FrozenModel


class Resolution(StrEnum):
    ACTION_TAKEN = "action_taken"  # the agent performed the business action (refund, change...)
    INFORMED = "informed"  # answered from knowledge or account data, no business action
    DECLINED = "declined"  # correctly refused, explaining why
    ESCALATED = "escalated"  # handed to a human with a reason code


class Fact(FrozenModel):
    """A fact that must (or must not) appear in what the customer is told."""

    id: str
    description: str
    patterns: tuple[str, ...]

    def present_in(self, text: str) -> bool:
        return any(re.search(p, text, flags=re.IGNORECASE) for p in self.patterns)


class ExpectedChange(FrozenModel):
    """A state change the oracle requires; ``match`` keys may be dotted paths into the entity."""

    collection: str
    kind: Literal["created", "updated", "deleted"]
    match: dict[str, Any]


class Expected(FrozenModel):
    resolution: Resolution
    changes: tuple[ExpectedChange, ...] = ()
    requires_clarification: bool = False
    escalation_reason: str | None = None
    required_ops: tuple[str, ...] = ()
    forbidden_ops: tuple[str, ...] = ()
    required_facts: tuple[Fact, ...] = ()
    forbidden_facts: tuple[Fact, ...] = ()
    gold_sections: tuple[str, ...] = ()
    rationale: str = ""


class TicketInput(FrozenModel):
    ticket_id: str
    subject: str
    body: str
    requester_email: str


class CaseProvenance(FrozenModel):
    generator: str
    generator_version: str
    scenario: str
    seed: int
    variant: int


Difficulty = Literal["easy", "medium", "hard"]
Split = Literal["dev", "test"]


class CaseDraft(FrozenModel):
    tenant_id: str
    scenario: str
    now: datetime
    ticket: TicketInput
    fixtures: dict[str, list[dict[str, Any]]]
    hidden_facts: dict[str, str]
    expected: Expected
    tags: tuple[str, ...] = ()
    difficulty: Difficulty = "easy"


class Case(CaseDraft):
    id: str
    split: Split
    provenance: CaseProvenance
