from collections.abc import Callable

from fdeops.llm.types import LLMRequest, LLMResponse, ToolCall

ScriptOutput = LLMResponse | str | ToolCall | list[ToolCall]


class ScriptedLLM:
    """Deterministic test double: a function decides each response from the request."""

    provider = "scripted"

    def __init__(self, responder: Callable[[LLMRequest], ScriptOutput]) -> None:
        self._responder = responder

    def complete(self, request: LLMRequest) -> LLMResponse:
        out = self._responder(request)
        if isinstance(out, LLMResponse):
            return out
        if isinstance(out, str):
            return LLMResponse(content=out, model=request.model, provider=self.provider)
        calls = (out,) if isinstance(out, ToolCall) else tuple(out)
        return LLMResponse(
            content="",
            tool_calls=calls,
            model=request.model,
            provider=self.provider,
            finish_reason="tool_calls",
        )
