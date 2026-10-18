"""The cost model of a tenant. Each value is an assumption with a range and a source."""

from pathlib import Path

from pydantic import model_validator

from fdeops.core.config import load_model
from fdeops.core.model import FrozenModel


class Assumption(FrozenModel):
    low: float
    likely: float
    high: float
    source: str

    @model_validator(mode="after")
    def _ordered(self) -> "Assumption":
        if not self.low <= self.likely <= self.high:
            raise ValueError("an assumption needs low <= likely <= high")
        if not self.source.strip():
            raise ValueError("an assumption needs a source")
        return self


class CostModel(FrozenModel):
    currency: str = "USD"
    staff_cost_per_hour: Assumption
    monthly_ticket_volume: Assumption
    adoption_rate: Assumption
    handling_minutes: dict[str, Assumption]
    rework_minutes: Assumption
    triage_saving_minutes: Assumption
    critical_error_cost: Assumption
    infrastructure_per_month: Assumption
    maintenance_per_month: Assumption
    integration_one_time: Assumption

    @model_validator(mode="after")
    def _default_category(self) -> "CostModel":
        if "default" not in self.handling_minutes:
            raise ValueError("handling_minutes needs a 'default' category")
        return self


def load_costs(path: Path) -> CostModel:
    return load_model(path, CostModel)


def category_of(tags: tuple[str, ...], costs: CostModel) -> str:
    """The first tag that has a handling time, else ``default``."""
    return next((t for t in tags if t in costs.handling_minutes and t != "default"), "default")
