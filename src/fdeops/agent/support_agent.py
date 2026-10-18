"""The agent loop.

One turn = model call, tool calls, repeat, until a terminal tool (reply / clarify / escalate)
succeeds or the step budget runs out. Every failure the model can cause (invalid JSON, unknown
tool, bad arguments, tool errors) comes back to it as a structured observation; nothing it emits
can crash the loop.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from fdeops.agent.config import AgentConfig
from fdeops.connectors.base import ConnectorRegistry, ErrorCode, OpContext, OpResult, ToolError
from fdeops.core.errors import FdeOpsError
from fdeops.core.hashing import canonical_json
from fdeops.core.model import FrozenModel
from fdeops.llm.cassette import CassetteMiss
from fdeops.llm.types import LLMClient, LLMRequest, LLMResponse, Message, ToolCall, ToolSpec, Usage
from fdeops.retrieval.retriever import RetrievedChunk, Retriever
from fdeops.trace.spans import SpanKind, Tracer

SEARCH_KB = ToolSpec(
    name="search_kb",
    description="Search the knowledge base. Returns the most relevant article sections.",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string", "minLength": 1}},
        "required": ["query"],
        "additionalProperties": False,
    },
)
NUDGE = (
    "You must finish by calling one of reply_to_customer, ask_clarifying_question or "
    "escalate_to_human. Do not answer in plain text."
)


class TurnOutcome(StrEnum):
    REPLY = "reply"
    CLARIFY = "clarify"
    ESCALATE = "escalate"
    BUDGET_EXHAUSTED = "budget_exhausted"
    MODEL_ERROR = "model_error"


class ToolCallRecord(FrozenModel):
    op: str
    args: dict[str, Any] | None
    ok: bool
    error_code: str | None
    latency_ms: float
    attempts: int
    mutating: bool
    terminal: str | None = None
    turn: int
    span_id: str


@dataclass
class TurnResult:
    outcome: TurnOutcome
    steps: int
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    retrieved: list[RetrievedChunk] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    llm_latency_ms: float = 0.0
    error: str | None = None


def format_chunks(chunks: list[RetrievedChunk]) -> str:
    return "\n\n".join(f"[{c.uid}] {c.title}\n{c.text}" for c in chunks) or "(no results)"


class SupportAgent:
    def __init__(
        self,
        config: AgentConfig,
        llm: LLMClient,
        registry: ConnectorRegistry,
        retriever: Retriever,
        tracer: Tracer,
    ) -> None:
        self.config = config
        self.llm = llm
        self.registry = registry
        self.retriever = retriever
        self.tracer = tracer
        self.tools = (
            SEARCH_KB,
            *(
                ToolSpec(name=s.name, description=s.description, parameters=s.parameters)
                for s in registry.specs()
            ),
        )

    def retrieve(self, query: str, now: datetime) -> list[RetrievedChunk]:
        with self.tracer.span(SpanKind.RETRIEVAL, "retrieve", **{"fdeops.query": query}) as span:
            chunks = self.retriever.search(query, now.date())
            span.set(
                **{
                    "fdeops.retrieved": [c.uid for c in chunks],
                    "fdeops.stale": [c.uid for c in chunks if c.stale],
                }
            )
        return chunks

    def run_turn(
        self, messages: list[Message], ctx: OpContext, now: datetime, turn: int, seed: int
    ) -> TurnResult:
        result = TurnResult(outcome=TurnOutcome.BUDGET_EXHAUSTED, steps=0)
        nudged = False
        with self.tracer.span(SpanKind.TURN, f"turn {turn}"):
            for _ in range(self.config.max_steps):
                result.steps += 1
                response = self._call_model(messages, seed, result)
                if response is None:
                    result.outcome = TurnOutcome.MODEL_ERROR
                    return result
                messages.append(
                    Message(
                        role="assistant", content=response.content, tool_calls=response.tool_calls
                    )
                )
                if not response.tool_calls:
                    if nudged:
                        continue
                    messages.append(Message(role="user", content=NUDGE))
                    nudged = True
                    continue
                terminal = self._run_tools(response.tool_calls, messages, ctx, now, turn, result)
                if terminal is not None:
                    result.outcome = terminal
                    return result
        return result

    def _call_model(
        self, messages: list[Message], seed: int, result: TurnResult
    ) -> LLMResponse | None:
        request = LLMRequest(
            model=self.config.model.name,
            messages=tuple(messages),
            tools=self.tools,
            temperature=self.config.model.temperature,
            max_tokens=self.config.model.max_tokens,
            seed=seed,
        )
        with self.tracer.span(
            SpanKind.LLM,
            "chat",
            **{
                "gen_ai.system": self.llm.provider,
                "gen_ai.request.model": request.model,
                "gen_ai.request.temperature": request.temperature,
            },
        ) as span:
            try:
                response = self.llm.complete(request)
            except CassetteMiss:
                raise  # a replay set that doesn't cover the run is a setup error, not agent quality
            except FdeOpsError as e:
                span.status, span.error = "error", f"{type(e).__name__}: {e}"
                result.error = span.error
                return None
            span.set(
                **{
                    "gen_ai.response.model": response.model,
                    "gen_ai.usage.input_tokens": response.usage.input_tokens,
                    "gen_ai.usage.output_tokens": response.usage.output_tokens,
                    "gen_ai.response.finish_reasons": [response.finish_reason],
                    "fdeops.latency_ms": response.latency_ms,
                    "fdeops.tool_calls": [c.name for c in response.tool_calls],
                }
            )
        result.usage = Usage(
            input_tokens=result.usage.input_tokens + response.usage.input_tokens,
            output_tokens=result.usage.output_tokens + response.usage.output_tokens,
        )
        result.llm_latency_ms += response.latency_ms
        return response

    def _run_tools(
        self,
        calls: tuple[ToolCall, ...],
        messages: list[Message],
        ctx: OpContext,
        now: datetime,
        turn: int,
        result: TurnResult,
    ) -> TurnOutcome | None:
        terminal: TurnOutcome | None = None
        for call in calls:
            if terminal is not None:
                messages.append(_tool_message(call, {"skipped": "turn already ended"}))
                continue
            with self.tracer.span(SpanKind.TOOL, call.name, **{"fdeops.op": call.name}) as span:
                op_result, payload = self._execute(call, ctx, now, result)
                span.set(
                    **{
                        "fdeops.ok": op_result.ok,
                        "fdeops.latency_ms": op_result.latency_ms,
                        "fdeops.attempts": op_result.attempts,
                        "fdeops.error_code": op_result.error.code if op_result.error else None,
                    }
                )
                if not op_result.ok:
                    span.status = "error"
                    span.error = op_result.error.message if op_result.error else None
            spec = self.registry.spec(call.name)
            result.tool_calls.append(
                ToolCallRecord(
                    op=call.name,
                    args=call.arguments,
                    ok=op_result.ok,
                    error_code=op_result.error.code if op_result.error else None,
                    latency_ms=op_result.latency_ms,
                    attempts=op_result.attempts,
                    mutating=bool(spec and spec.mutating),
                    terminal=spec.terminal if spec else None,
                    turn=turn,
                    span_id=span.span_id,
                )
            )
            messages.append(_tool_message(call, payload))
            if op_result.ok and spec is not None and spec.terminal is not None:
                terminal = TurnOutcome(spec.terminal)
        return terminal

    def _execute(
        self, call: ToolCall, ctx: OpContext, now: datetime, result: TurnResult
    ) -> tuple[OpResult, dict[str, Any]]:
        if call.arguments is None:
            err = ToolError.of(
                ErrorCode.INVALID_ARGUMENT,
                f"arguments are not a JSON object: {call.raw_arguments[:200]!r}",
            )
            return OpResult.failure(err), {"error": err.model_dump(mode="json")}
        if call.name == SEARCH_KB.name:
            query = call.arguments.get("query")
            if not isinstance(query, str) or not query.strip():
                err = ToolError.of(ErrorCode.INVALID_ARGUMENT, "query must be a non-empty string")
                return OpResult.failure(err), {"error": err.model_dump(mode="json")}
            chunks = self.retrieve(query, now)
            result.retrieved.extend(chunks)
            return OpResult(ok=True), {"ok": True, "results": format_chunks(chunks)}
        op_result = self.registry.call(call.name, call.arguments, ctx)
        if op_result.ok:
            return op_result, {"ok": True, "data": op_result.data}
        assert op_result.error is not None
        return op_result, {"error": op_result.error.model_dump(mode="json")}


def _tool_message(call: ToolCall, payload: dict[str, Any]) -> Message:
    return Message(
        role="tool",
        content=json.dumps(json.loads(canonical_json(payload))),
        tool_call_id=call.id,
        name=call.name,
    )
