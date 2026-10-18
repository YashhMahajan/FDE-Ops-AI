"""Uniform connector interface.

Every external system (or simulated one) is exposed as named operations with JSON-Schema
parameters. Calls never raise: failures come back as typed ``ToolError``s the agent can reason
about (retry, ask, escalate) and the evaluator can classify.
"""

import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, Protocol

import jsonschema

from fdeops.core.clock import Clock
from fdeops.core.errors import FdeOpsError
from fdeops.core.model import FrozenModel


class ErrorCode(StrEnum):
    NOT_FOUND = "NOT_FOUND"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    CONFLICT = "CONFLICT"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    INTERNAL = "INTERNAL"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"


RETRYABLE = frozenset({ErrorCode.TIMEOUT, ErrorCode.UNAVAILABLE, ErrorCode.RATE_LIMITED})


class ToolError(FrozenModel):
    code: ErrorCode
    message: str
    retryable: bool = False

    @classmethod
    def of(cls, code: ErrorCode, message: str) -> "ToolError":
        return cls(code=code, message=message, retryable=code in RETRYABLE)


class OpFailure(FdeOpsError):
    def __init__(self, error: ToolError) -> None:
        self.error = error
        super().__init__(f"{error.code}: {error.message}")

    @classmethod
    def of(cls, code: ErrorCode, message: str) -> "OpFailure":
        return cls(ToolError.of(code, message))


Terminal = Literal["reply", "clarify", "escalate"]


class OpSpec(FrozenModel):
    name: str
    description: str
    parameters: dict[str, Any]
    mutating: bool
    required_scope: str
    terminal: Terminal | None = None


@dataclass
class OpContext:
    tenant_id: str
    actor: str
    scopes: frozenset[str]
    clock: Clock
    case_id: str | None = None
    idempotency_key: str | None = None
    tags: frozenset[str] = field(default_factory=frozenset)


class OpResult(FrozenModel):
    ok: bool
    data: Any = None
    error: ToolError | None = None
    latency_ms: float = 0.0
    attempts: int = 1

    @classmethod
    def failure(cls, error: ToolError, latency_ms: float = 0.0) -> "OpResult":
        return cls(ok=False, error=error, latency_ms=latency_ms)


class Connector(Protocol):
    name: str

    def ops(self) -> list[OpSpec]: ...

    def call(self, op: str, args: dict[str, Any], ctx: OpContext) -> OpResult: ...


Handler = Callable[[dict[str, Any], OpContext], Any]


class InProcessConnector:
    """Connector backed by Python handlers. Handlers signal failure by raising ``OpFailure``."""

    def __init__(self, name: str, handlers: Mapping[str, tuple[OpSpec, Handler]]) -> None:
        self.name = name
        self._handlers = dict(handlers)
        for op, (spec, _) in self._handlers.items():
            if spec.name != op:
                raise ValueError(f"handler key {op!r} does not match spec name {spec.name!r}")
            jsonschema.Draft202012Validator.check_schema(spec.parameters)

    def ops(self) -> list[OpSpec]:
        return [spec for spec, _ in self._handlers.values()]

    def call(self, op: str, args: dict[str, Any], ctx: OpContext) -> OpResult:
        entry = self._handlers.get(op)
        if entry is None:
            return OpResult.failure(
                ToolError.of(ErrorCode.INVALID_ARGUMENT, f"unknown operation {op!r}")
            )
        spec, handler = entry
        start = time.perf_counter()
        try:
            jsonschema.validate(args, spec.parameters)
        except jsonschema.ValidationError as e:
            path = ".".join(str(p) for p in e.absolute_path) or "(root)"
            return OpResult.failure(
                ToolError.of(
                    ErrorCode.INVALID_ARGUMENT, f"invalid arguments at {path}: {e.message}"
                )
            )
        try:
            data = handler(args, ctx)
        except OpFailure as f:
            return OpResult.failure(f.error, _elapsed_ms(start))
        except Exception as e:  # a bug in a handler must not crash the agent loop
            return OpResult.failure(
                ToolError.of(ErrorCode.INTERNAL, f"{type(e).__name__}: {e}"), _elapsed_ms(start)
            )
        return OpResult(ok=True, data=data, latency_ms=_elapsed_ms(start))


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


class ConnectorRegistry:
    """Routes operations to the connector that owns them. Operation names are globally unique."""

    def __init__(self, connectors: Iterable[Connector]) -> None:
        self._route: dict[str, tuple[Connector, OpSpec]] = {}
        for c in connectors:
            for spec in c.ops():
                if spec.name in self._route:
                    raise ValueError(
                        f"operation {spec.name!r} is provided by more than one connector"
                    )
                self._route[spec.name] = (c, spec)

    def specs(self) -> list[OpSpec]:
        return [spec for _, spec in self._route.values()]

    def spec(self, op: str) -> OpSpec | None:
        entry = self._route.get(op)
        return entry[1] if entry else None

    def call(self, op: str, args: dict[str, Any], ctx: OpContext) -> OpResult:
        entry = self._route.get(op)
        if entry is None:
            return OpResult.failure(
                ToolError.of(ErrorCode.INVALID_ARGUMENT, f"unknown operation {op!r}")
            )
        return entry[0].call(op, args, ctx)
