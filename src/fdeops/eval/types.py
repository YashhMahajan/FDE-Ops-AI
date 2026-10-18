from dataclasses import dataclass
from typing import Any, Protocol

from fdeops.agent.episode import EpisodeResult
from fdeops.core.model import FrozenModel
from fdeops.tenancy.loader import Tenant
from fdeops.world.cases import Case


class Score(FrozenModel):
    evaluator: str
    name: str
    value: float | None
    """``None`` when no measurement exists (e.g. a judge produced no usable verdict)."""
    passed: bool | None
    """``None`` means "not applicable / informational", never "passed"."""
    critical: bool = False
    details: dict[str, Any] = {}


@dataclass(frozen=True)
class EvalContext:
    tenant: Tenant


class Evaluator(Protocol):
    name: str

    def evaluate(self, case: Case, ep: EpisodeResult, ctx: EvalContext) -> list[Score]: ...
