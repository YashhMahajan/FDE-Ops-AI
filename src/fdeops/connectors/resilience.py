"""Timeouts, retries with backoff, circuit breaking, rate limiting and idempotency.

The subtle case is a *mutating* call that succeeds upstream but whose response arrives too late:
the caller sees a timeout and retries. Every logical mutating call therefore carries one
idempotency key, reused across its retries, so the upstream API can recognise the repeat and the
refund happens exactly once.
"""

import dataclasses
import random
from typing import Any, Literal

from fdeops.connectors.base import Connector, ErrorCode, OpContext, OpResult, OpSpec, ToolError
from fdeops.core.clock import Clock
from fdeops.core.errors import InvariantError
from fdeops.core.ids import stable_id
from fdeops.core.model import FrozenModel


class RetryPolicy(FrozenModel):
    max_attempts: int = 3
    base_delay_s: float = 0.2
    max_delay_s: float = 2.0
    jitter: float = 0.1

    def delay(self, attempt: int, rng: random.Random) -> float:
        base = min(self.base_delay_s * 2 ** (attempt - 1), self.max_delay_s)
        return float(max(0.0, base * (1 + self.jitter * rng.uniform(-1, 1))))


class CircuitBreaker:
    def __init__(
        self, failure_threshold: int = 5, reset_after_s: float = 30.0, clock: Clock | None = None
    ) -> None:
        if clock is None:
            raise InvariantError("CircuitBreaker needs a clock")
        self.failure_threshold = failure_threshold
        self.reset_after_s = reset_after_s
        self.clock = clock
        self._failures = 0
        self._opened_at: Any = None

    @property
    def state(self) -> Literal["closed", "open", "half_open"]:
        if self._opened_at is None:
            return "closed"
        elapsed = (self.clock.now() - self._opened_at).total_seconds()
        return "half_open" if elapsed >= self.reset_after_s else "open"

    def allow(self) -> bool:
        return self.state != "open"

    def record(self, success: bool) -> None:
        if success:
            self._failures, self._opened_at = 0, None
            return
        self._failures += 1
        if self.state == "half_open" or self._failures >= self.failure_threshold:
            self._opened_at = self.clock.now()


class TokenBucket:
    def __init__(self, rate_per_s: float, burst: int, clock: Clock) -> None:
        self.rate, self.burst, self.clock = rate_per_s, burst, clock
        self._tokens = float(burst)
        self._last = clock.now()

    def try_acquire(self) -> bool:
        now = self.clock.now()
        self._tokens = min(
            self.burst, self._tokens + (now - self._last).total_seconds() * self.rate
        )
        self._last = now
        if self._tokens >= 1:
            self._tokens -= 1
            return True
        return False


class ResilientConnector:
    def __init__(
        self,
        inner: Connector,
        *,
        retry: RetryPolicy,
        breaker: CircuitBreaker | None,
        limiter: TokenBucket | None,
        timeout_s: float,
        clock: Clock,
        rng: random.Random,
    ) -> None:
        self.inner = inner
        self.name = inner.name
        self.retry, self.breaker, self.limiter = retry, breaker, limiter
        self.timeout_s, self.clock, self.rng = timeout_s, clock, rng
        self._specs = {s.name: s for s in inner.ops()}
        self._seq: dict[str, int] = {}

    def ops(self) -> list[OpSpec]:
        return list(self._specs.values())

    def _with_key(self, op: str, args: dict[str, Any], ctx: OpContext) -> OpContext:
        spec = self._specs.get(op)
        if spec is None or not spec.mutating or ctx.idempotency_key:
            return ctx
        base = stable_id("call", op, args)
        n = self._seq.get(base, 0)
        self._seq[base] = n + 1
        return dataclasses.replace(ctx, idempotency_key=stable_id("idem", ctx.case_id, op, args, n))

    def call(self, op: str, args: dict[str, Any], ctx: OpContext) -> OpResult:
        ctx = self._with_key(op, args, ctx)
        total_ms = 0.0
        result = OpResult.failure(ToolError.of(ErrorCode.INTERNAL, "no attempt made"))
        for attempt in range(1, self.retry.max_attempts + 1):
            if self.limiter is not None and not self.limiter.try_acquire():
                result = OpResult.failure(
                    ToolError.of(ErrorCode.RATE_LIMITED, "client-side rate limit")
                )
            elif self.breaker is not None and not self.breaker.allow():
                return OpResult(
                    ok=False,
                    error=ToolError(
                        code=ErrorCode.UNAVAILABLE,
                        message=f"circuit open for {self.name}",
                        retryable=False,
                    ),
                    latency_ms=total_ms,
                    attempts=attempt,
                )
            else:
                result = self.inner.call(op, args, ctx)
                if result.latency_ms > self.timeout_s * 1000:
                    result = OpResult.failure(
                        ToolError.of(ErrorCode.TIMEOUT, f"no response within {self.timeout_s:g}s"),
                        latency_ms=self.timeout_s * 1000,
                    )
                if self.breaker is not None:
                    failed_infra = result.error is not None and result.error.retryable
                    self.breaker.record(not failed_infra)
            total_ms += result.latency_ms
            done = result.ok or result.error is None or not result.error.retryable
            if done or attempt == self.retry.max_attempts:
                return result.model_copy(update={"attempts": attempt, "latency_ms": total_ms})
            pause = self.retry.delay(attempt, self.rng)
            self.clock.sleep(pause)
            total_ms += pause * 1000
        return result
