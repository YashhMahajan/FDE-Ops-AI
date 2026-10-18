from typing import Any

from fdeops.connectors.audit import AuditLog
from fdeops.connectors.base import Connector, ErrorCode, OpContext, OpResult, OpSpec, ToolError


class PermissionGuard:
    """Enforces scopes before anything runs and audits every mutating call and every denial."""

    def __init__(self, inner: Connector, audit: AuditLog) -> None:
        self.inner = inner
        self.name = inner.name
        self.audit = audit
        self._specs = {s.name: s for s in inner.ops()}

    def ops(self) -> list[OpSpec]:
        return list(self._specs.values())

    def call(self, op: str, args: dict[str, Any], ctx: OpContext) -> OpResult:
        spec = self._specs.get(op)
        if spec is None:
            return self.inner.call(op, args, ctx)
        if spec.required_scope not in ctx.scopes:
            self.audit.append(
                at=ctx.clock.now(),
                tenant_id=ctx.tenant_id,
                actor=ctx.actor,
                action="call",
                op=op,
                args=args,
                outcome="denied",
            )
            return OpResult.failure(
                ToolError.of(ErrorCode.PERMISSION_DENIED, f"missing scope {spec.required_scope!r}")
            )
        result = self.inner.call(op, args, ctx)
        if spec.mutating:
            outcome = "ok" if result.ok else (result.error.code if result.error else "error")
            self.audit.append(
                at=ctx.clock.now(),
                tenant_id=ctx.tenant_id,
                actor=ctx.actor,
                action="call",
                op=op,
                args=args,
                outcome=str(outcome),
            )
        return result
