"""Spans and traces.

Attribute names follow the OpenTelemetry GenAI semantic conventions where one exists
(``gen_ai.request.model``, ``gen_ai.usage.input_tokens``...), and use the ``fdeops.`` namespace
otherwise. Wall-clock duration comes from the injected clock; the latency a model or tool call
actually took is recorded separately as ``fdeops.latency_ms`` so it survives cassette replay.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel

from fdeops.core.clock import Clock
from fdeops.core.ids import new_id
from fdeops.core.model import FrozenModel


class SpanKind(StrEnum):
    AGENT = "agent"
    TURN = "turn"
    LLM = "llm"
    RETRIEVAL = "retrieval"
    TOOL = "tool"
    GUARD = "guard"


class Span(BaseModel):
    span_id: str
    parent_id: str | None
    trace_id: str
    kind: SpanKind
    name: str
    start: datetime
    end: datetime | None = None
    attributes: dict[str, Any] = {}
    status: Literal["ok", "error"] = "ok"
    error: str | None = None

    def set(self, **attributes: Any) -> None:
        self.attributes.update(attributes)

    @property
    def duration_ms(self) -> float:
        if self.end is None:
            return 0.0
        return (self.end - self.start).total_seconds() * 1000


class Trace(FrozenModel):
    trace_id: str
    spans: tuple[Span, ...]

    def by_kind(self, kind: SpanKind) -> list[Span]:
        return [s for s in self.spans if s.kind == kind]

    def children(self, span_id: str) -> list[Span]:
        return [s for s in self.spans if s.parent_id == span_id]

    def get(self, span_id: str) -> Span | None:
        return next((s for s in self.spans if s.span_id == span_id), None)


class Tracer:
    """Builds one trace. Not shared across threads: each episode gets its own tracer."""

    def __init__(self, trace_id: str, clock: Clock) -> None:
        self.trace_id = trace_id
        self._clock = clock
        self._spans: list[Span] = []
        self._stack: list[Span] = []

    @contextmanager
    def span(self, kind: SpanKind, name: str, **attributes: Any) -> Iterator[Span]:
        span = Span(
            span_id=new_id("spn"),
            parent_id=self._stack[-1].span_id if self._stack else None,
            trace_id=self.trace_id,
            kind=kind,
            name=name,
            start=self._clock.now(),
            attributes=dict(attributes),
        )
        self._spans.append(span)
        self._stack.append(span)
        try:
            yield span
        except BaseException as e:
            span.status = "error"
            span.error = f"{type(e).__name__}: {e}"
            raise
        finally:
            span.end = self._clock.now()
            self._stack.pop()

    def trace(self) -> Trace:
        return Trace(trace_id=self.trace_id, spans=tuple(self._spans))
