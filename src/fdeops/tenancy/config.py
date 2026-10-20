from datetime import datetime
from typing import Any, Literal

from fdeops.core.model import FrozenModel
from fdeops.trace.redact import PIIConfig
from fdeops.world.dataset import DatasetSpec


class TenantWorld(FrozenModel):
    now: datetime
    spec: dict[str, Any]


class TenantConfig(FrozenModel):
    id: str
    display_name: str
    fictional: Literal[True]
    pack: str
    policy_file: str = "policy.yaml"
    kb_dir: str = "kb"
    world: TenantWorld
    datasets: list[DatasetSpec] = []
    agent_scopes: tuple[str, ...]
    pii: PIIConfig = PIIConfig()
    notes: str = ""
    demo_incident: str | None = None
    """The incident file (in ``incidents/<tenant id>/``, without ``.yaml``) of the flagship demo."""
