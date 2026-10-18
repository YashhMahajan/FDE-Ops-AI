"""Client for any OpenAI-compatible chat-completions endpoint.

"OpenAI-compatible" names the wire format only: this client talks to OpenRouter (free models),
vLLM and llama.cpp servers (open models on free cloud GPUs), and Ollama. It never needs an OpenAI
account. Tool-call arguments that are not a JSON object are
kept raw and surfaced as ``arguments=None`` so the agent loop can return a structured error to the
model instead of crashing.
"""

import json
import time
from typing import Any

import httpx

from fdeops.core.errors import FdeOpsError
from fdeops.llm.types import LLMRequest, LLMResponse, Message, ToolCall, Usage


class LLMUnavailable(FdeOpsError):
    def __init__(self, message: str, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


def _message_to_wire(m: Message) -> dict[str, Any]:
    out: dict[str, Any] = {"role": m.role, "content": m.content}
    if m.tool_calls:
        out["tool_calls"] = [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.name, "arguments": c.raw_arguments},
            }
            for c in m.tool_calls
        ]
    if m.role == "tool":
        out["tool_call_id"] = m.tool_call_id
    return out


def _parse_arguments(raw: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


class OpenAICompatibleLLM:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_s: float = 120.0,
        client: httpx.Client | None = None,
        provider: str = "openai_compatible",
        headers: dict[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model
        self.provider = provider
        self._headers = dict(headers or {})
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._client = client or httpx.Client(
            base_url=base_url, timeout=timeout_s, transport=transport
        )

    def complete(self, request: LLMRequest) -> LLMResponse:
        body: dict[str, Any] = {
            "model": request.model or self.model,
            "messages": [_message_to_wire(m) for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.seed is not None:
            body["seed"] = request.seed
        if request.tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in request.tools
            ]
        start = time.perf_counter()
        try:
            r = self._client.post("/chat/completions", json=body, headers=self._headers)
        except httpx.TransportError as e:
            raise LLMUnavailable(f"transport error: {e}", retryable=True) from e
        latency_ms = (time.perf_counter() - start) * 1000
        if r.status_code >= 400:
            retryable = r.status_code == 429 or r.status_code >= 500
            raise LLMUnavailable(f"HTTP {r.status_code}: {r.text[:300]}", retryable=retryable)
        data = r.json()
        choice = data["choices"][0]
        msg = choice.get("message", {})
        calls = tuple(
            ToolCall(
                id=c.get("id") or f"call_{i}",
                name=c["function"]["name"],
                arguments=_parse_arguments(c["function"].get("arguments") or ""),
                raw_arguments=c["function"].get("arguments") or "",
            )
            for i, c in enumerate(msg.get("tool_calls") or [])
        )
        usage = data.get("usage") or {}
        return LLMResponse(
            content=msg.get("content") or "",
            tool_calls=calls,
            usage=Usage(
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
            ),
            latency_ms=latency_ms,
            model=data.get("model", request.model),
            provider=self.provider,
            finish_reason=choice.get("finish_reason") or "stop",
        )
