from enum import StrEnum
from typing import Any, Literal, Protocol

from fdeops.core.model import FrozenModel

Role = Literal["system", "user", "assistant", "tool"]


class ToolCall(FrozenModel):
    id: str
    name: str
    arguments: dict[str, Any] | None
    """Parsed arguments, or ``None`` when the model emitted invalid JSON (see ``raw_arguments``)."""
    raw_arguments: str


class Message(FrozenModel):
    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    name: str | None = None


class ToolSpec(FrozenModel):
    name: str
    description: str
    parameters: dict[str, Any]


class LLMRequest(FrozenModel):
    model: str
    messages: tuple[Message, ...]
    tools: tuple[ToolSpec, ...] = ()
    temperature: float = 0.0
    max_tokens: int = 1024
    seed: int | None = None


class Usage(FrozenModel):
    input_tokens: int = 0
    output_tokens: int = 0


class LLMResponse(FrozenModel):
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage = Usage()
    latency_ms: float = 0.0
    model: str
    provider: str
    finish_reason: str = "stop"


class LLMClient(Protocol):
    provider: str

    def complete(self, request: LLMRequest) -> LLMResponse: ...


class LLMMode(StrEnum):
    LIVE = "live"  # call the provider, record nothing
    RECORD = "record"  # call the provider and save every response
    REPLAY = "replay"  # serve saved responses only; a miss is an error
    REPLAY_OR_RECORD = "replay_or_record"  # serve saved responses, record misses
