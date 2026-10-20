"""Monitor configuration for each tenant (``monitors.yaml``).

Each monitor must tell why it exists.
"""

from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator

from fdeops.core.config import load_model
from fdeops.core.model import FrozenModel
from fdeops.monitor.signals import RATE_SIGNALS, VALUE_SIGNALS


class MonitorSpec(FrozenModel):
    signal: str
    direction: Literal["up", "down"] = "up"
    tolerance: float
    """For a rate: the permitted absolute change. For a value: the permitted relative change."""
    statistic: Literal["rate", "p95", "mean"] = "rate"
    shift: float = 0.10
    """For a rate: the change that the sequential detector (CUSUM) must find quickly."""
    min_samples: int = 30
    severity: Literal["page", "ticket"] = "ticket"
    why: str

    @field_validator("why")
    @classmethod
    def _explained(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("each monitor must explain why it exists")
        return v

    @model_validator(mode="after")
    def _known_signal(self) -> "MonitorSpec":
        if self.statistic == "rate" and self.signal not in RATE_SIGNALS:
            raise ValueError(f"{self.signal} is not a rate signal: {sorted(RATE_SIGNALS)}")
        if self.statistic != "rate" and self.signal not in VALUE_SIGNALS:
            raise ValueError(f"{self.signal} is not a value signal: {sorted(VALUE_SIGNALS)}")
        if self.tolerance < 0 or not 0 < self.shift < 1:
            raise ValueError("tolerance must be zero or more, and shift must be between 0 and 1")
        return self


class MonitorConfig(FrozenModel):
    cusum_threshold: float = 3.0
    """The CUSUM alarm level. A larger value gives fewer false alarms and a slower detection."""
    monitors: tuple[MonitorSpec, ...]


def load_monitors(path: Path) -> MonitorConfig:
    return load_model(path, MonitorConfig)
