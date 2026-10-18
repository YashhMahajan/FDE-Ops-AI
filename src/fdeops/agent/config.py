from pathlib import Path
from typing import Literal

from fdeops.connectors.resilience import RetryPolicy
from fdeops.core.config import load_model
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
