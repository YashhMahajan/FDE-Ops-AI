"""Checks every action against business policy *before* it runs, using only what a production
guardrail could see (current state and who is asking).

``observe`` records violations of actions that actually executed (for grading and diagnosis);
``enforce`` blocks actions with critical violations. Switching a tenant from observe to enforce is
one of the remediations the improvement loop can propose and validate.
"""

from datetime import datetime
from typing import Any, Literal, Protocol

from fdeops.connectors.base import Connector, ErrorCode, OpContext, OpResult, OpSpec, ToolError
from fdeops.world.policy import Violation


class _Checker(Protocol):
    def check(
        self, op: str, args: dict[str, Any], state: Any, requester_email: str, now: datetime
    ) -> list[Violation]: ...


class PolicyMonitor:
    def __init__(
        self,
        inner: Connector,
        checker: _Checker,
        state: Any,
        requester_email: str,
        mode: Literal["observe", "enforce"] = "observe",
    ) -> None:
        self.inner = inner
        self.name = inner.name
        self.checker = checker
        self.state = state
        self.requester_email = requester_email
        self.mode = mode
        self.violations: list[Violation] = []
        self.blocked: list[Violation] = []

    def ops(self) -> list[OpSpec]:
        return self.inner.ops()

    def call(self, op: str, args: dict[str, Any], ctx: OpContext) -> OpResult:
        found = self.checker.check(op, args, self.state, self.requester_email, ctx.clock.now())
        critical = [v for v in found if v.severity == "critical"]
        if self.mode == "enforce" and critical:
            self.blocked.extend(found)
            rules = ", ".join(v.rule for v in critical)
            return OpResult.failure(
                ToolError.of(ErrorCode.PERMISSION_DENIED, f"blocked by policy: {rules}")
            )
        result = self.inner.call(op, args, ctx)
        if result.ok:
            self.violations.extend(found)
        return result
