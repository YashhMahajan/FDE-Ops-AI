"""Declarative fault injection: the chaos-engineering half of the simulated world."""

import random
from typing import Any, Literal

from fdeops.connectors.base import Connector, ErrorCode, OpContext, OpResult, OpSpec, ToolError
from fdeops.core.model import FrozenModel

FaultKind = Literal[
    "timeout_after_success",
    "timeout",
    "error_5xx",
    "rate_limit",
    "malformed",
    "expired_credential",
    "schema_mismatch",
]
SLOW_MS = 60_000.0


class FaultRule(FrozenModel):
    op: str  # operation name or "*"
    kind: FaultKind
    probability: float = 1.0
    times: int | None = None
    only_mutating: bool = False
    """Apply the fault only to operations that change data (where a retry can cause harm)."""


class FaultInjectingConnector:
    def __init__(self, inner: Connector, rules: list[FaultRule], rng: random.Random) -> None:
        self.inner = inner
        self.name = inner.name
        self.rules = rules
        self.rng = rng
        self._fired = [0] * len(rules)
        self.injected: list[tuple[str, str]] = []
        self._ops = {s.name for s in inner.ops()}
        self._mutating = {s.name for s in inner.ops() if s.mutating}

    def ops(self) -> list[OpSpec]:
        return self.inner.ops()

    def _pick(self, op: str) -> FaultRule | None:
        for i, rule in enumerate(self.rules):
            if rule.op not in ("*", op) or op not in self._ops:
                continue
            if rule.only_mutating and op not in self._mutating:
                continue
            if rule.times is not None and self._fired[i] >= rule.times:
                continue
            if self.rng.random() < rule.probability:
                self._fired[i] += 1
                return rule
        return None

    def call(self, op: str, args: dict[str, Any], ctx: OpContext) -> OpResult:
        rule = self._pick(op)
        if rule is None:
            return self.inner.call(op, args, ctx)
        self.injected.append((op, rule.kind))
        if rule.kind == "timeout_after_success":
            return self.inner.call(op, args, ctx).model_copy(update={"latency_ms": SLOW_MS})
        if rule.kind == "malformed":
            real = self.inner.call(op, args, ctx)
            fields = sorted(real.data) if isinstance(real.data, dict) else []
            missing = self.rng.choice(fields) if fields else "body"
            return OpResult.failure(
                ToolError.of(
                    ErrorCode.MALFORMED_RESPONSE, f"upstream response missing field {missing!r}"
                )
            )
        errors: dict[str, tuple[ErrorCode, str, float]] = {
            "timeout": (ErrorCode.TIMEOUT, "upstream did not respond", SLOW_MS),
            "error_5xx": (ErrorCode.UNAVAILABLE, "upstream returned HTTP 503", 30.0),
            "rate_limit": (ErrorCode.RATE_LIMITED, "upstream returned HTTP 429", 10.0),
            "expired_credential": (ErrorCode.UNAUTHENTICATED, "credential expired", 10.0),
            "schema_mismatch": (
                ErrorCode.INVALID_ARGUMENT,
                "the upstream API rejected the request: unknown field (schema version 2)",
                15.0,
            ),
        }
        code, message, latency = errors[rule.kind]
        return OpResult.failure(ToolError.of(code, message), latency_ms=latency)
