from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from fdeops.connectors.resilience import RetryPolicy
from fdeops.core.config import format_validation_error, load_model
from fdeops.core.errors import ConfigError
from fdeops.core.hashing import content_hash
from fdeops.core.model import FrozenModel
from fdeops.retrieval.retriever import RetrievalConfig


class ModelRef(FrozenModel):
    provider: str
    name: str
    temperature: float = 0.0
    max_tokens: int = 1024


class AgentConfig(FrozenModel):
    """Everything that defines agent behavior. Its hash identifies a release candidate."""

    id: str
    model: ModelRef
    prompt_version: str = "support_v1"
    retrieval: RetrievalConfig = RetrievalConfig()
    auto_context: bool = True
    oracle_context: bool = False
    """Diagnosis only: give the gold sections of the case as the only excerpts. It shows the
    result with perfect retrieval. It is never a production setting."""
    max_steps: int = 8
    max_turns: int = 3
    policy_guardrail: Literal["observe", "enforce"] = "observe"
    tool_timeout_s: float = 5.0
    retry: RetryPolicy = RetryPolicy()

    @property
    def content_hash(self) -> str:
        # Not cached: pydantic's model_copy would copy a cached value into a changed copy.
        return content_hash(self.model_dump(exclude={"id"}))


def load_agent_config(path: Path) -> AgentConfig:
    return load_model(path, AgentConfig)


def _merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in patch.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def apply_patch(config: AgentConfig, patch: dict[str, Any]) -> AgentConfig:
    try:
        return AgentConfig.model_validate(_merge(config.model_dump(mode="json"), patch))
    except ValidationError as e:
        raise ConfigError(f"intervention patch is not valid: {format_validation_error(e)}") from e
