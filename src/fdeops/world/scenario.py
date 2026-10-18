import random
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from fdeops.retrieval.kb import KnowledgeBase
from fdeops.world.cases import CaseDraft
from fdeops.world.state import WorldState


@dataclass(frozen=True)
class ScenarioContext:
    rng: random.Random
    base_world: WorldState
    policy: Any
    kb: KnowledgeBase
    now: datetime
    tenant_id: str
    variant: int


class Scenario(Protocol):
    id: str

    def generate(self, ctx: ScenarioContext) -> CaseDraft: ...
