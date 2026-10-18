import random
from datetime import UTC, datetime, timedelta
from typing import Any

from fdeops.connectors.audit import AuditLog
from fdeops.connectors.base import (
    ErrorCode,
    InProcessConnector,
    OpContext,
    OpFailure,
    OpResult,
    OpSpec,
    ToolError,
)
from fdeops.connectors.faults import FaultInjectingConnector, FaultRule
from fdeops.connectors.guard import PermissionGuard
from fdeops.connectors.policy_monitor import PolicyMonitor
from fdeops.connectors.resilience import (
    CircuitBreaker,
    ResilientConnector,
    RetryPolicy,
    TokenBucket,
)
from fdeops.core.clock import FakeClock
from fdeops.packs.billing.entities import Customer, Invoice, User
from fdeops.packs.billing.ops import AGENT_SCOPES, build_billing_connectors
from fdeops.packs.billing.policy import BillingPolicy, BillingPolicyEngine
from fdeops.packs.billing.state import BillingState
from fdeops.world.policy import Violation

NOW = datetime(2026, 9, 15, tzinfo=UTC)
SCHEMA = {"type": "object"}


def ctx(clock: FakeClock, scopes: frozenset[str] = frozenset({"s"})) -> OpContext:
    return OpContext(tenant_id="t", actor="agent", scopes=scopes, clock=clock, case_id="case_1")


class Scripted:
    """Connector returning queued results, recording the idempotency key of every call."""

    name = "scripted"

    def __init__(self, results: list[OpResult], mutating: bool = False) -> None:
        self.results = results
        self.keys: list[str | None] = []
        self.mutating = mutating

    def ops(self) -> list[OpSpec]:
        return [
            OpSpec(
                name="op",
                description="",
                parameters=SCHEMA,
                mutating=self.mutating,
                required_scope="s",
            )
        ]

    def call(self, op: str, args: dict[str, Any], c: OpContext) -> OpResult:
        self.keys.append(c.idempotency_key)
        return self.results.pop(0)


def err(code: ErrorCode) -> OpResult:
    return OpResult.failure(ToolError.of(code, "x"))


def resilient(inner: Any, clock: FakeClock, **kw: Any) -> ResilientConnector:
    return ResilientConnector(
        inner,
        retry=RetryPolicy(max_attempts=3, base_delay_s=0.1, jitter=0),
        breaker=kw.get("breaker"),
        limiter=kw.get("limiter"),
        timeout_s=kw.get("timeout_s", 5.0),
        clock=clock,
        rng=random.Random(0),
    )


def test_retries_retryable_then_succeeds() -> None:
    clock = FakeClock(NOW)
    inner = Scripted(
        [err(ErrorCode.UNAVAILABLE), err(ErrorCode.TIMEOUT), OpResult(ok=True, data=1)]
    )
    r = resilient(inner, clock).call("op", {}, ctx(clock))
    assert r.ok and r.attempts == 3
    assert clock.now() - NOW == timedelta(seconds=0.1 + 0.2)


def test_non_retryable_not_retried() -> None:
    clock = FakeClock(NOW)
    inner = Scripted([err(ErrorCode.CONFLICT), OpResult(ok=True)])
    r = resilient(inner, clock).call("op", {}, ctx(clock))
    assert r.error is not None and r.error.code == ErrorCode.CONFLICT and r.attempts == 1


def test_gives_up_after_max_attempts() -> None:
    clock = FakeClock(NOW)
    inner = Scripted([err(ErrorCode.UNAVAILABLE)] * 3)
    r = resilient(inner, clock).call("op", {}, ctx(clock))
    assert not r.ok and r.attempts == 3


def test_slow_result_becomes_timeout() -> None:
    clock = FakeClock(NOW)
    inner = Scripted([OpResult(ok=True, latency_ms=9000)] * 3)
    r = resilient(inner, clock, timeout_s=2.0).call("op", {}, ctx(clock))
    assert r.error is not None and r.error.code == ErrorCode.TIMEOUT


def test_same_idempotency_key_reused_across_retries() -> None:
    clock = FakeClock(NOW)
    inner = Scripted([err(ErrorCode.UNAVAILABLE), OpResult(ok=True)], mutating=True)
    resilient(inner, clock).call("op", {"a": 1}, ctx(clock))
    assert inner.keys[0] is not None and inner.keys[0] == inner.keys[1]


def _billing_state() -> BillingState:
    s = BillingState()
    s.upsert(
        "customers",
        Customer(
            id="cus_1",
            company="C",
            plan_id="p",
            status="active",
            created_at=NOW - timedelta(days=90),
        ),
    )
    s.upsert(
        "users", User(id="u1", customer_id="cus_1", email="o@c.example", name="O", role="owner")
    )
    s.upsert(
        "invoices",
        Invoice(
            id="inv_1",
            customer_id="cus_1",
            amount_cents=9900,
            period_start=NOW.date(),
            period_end=NOW.date(),
            issued_at=NOW - timedelta(days=2),
            paid_at=NOW - timedelta(days=2),
            status="paid",
        ),
    )
    return s


def test_timeout_after_success_retry_does_not_double_refund() -> None:
    clock = FakeClock(NOW)
    state = _billing_state()
    billing = next(c for c in build_billing_connectors(state) if c.name == "billing")
    faulty = FaultInjectingConnector(
        billing,
        [FaultRule(op="issue_refund", kind="timeout_after_success", times=1)],
        random.Random(1),
    )
    r = resilient(faulty, clock, timeout_s=2.0).call(
        "issue_refund",
        {"invoice_id": "inv_1", "amount_cents": 9900, "reason": "x"},
        ctx(clock, AGENT_SCOPES),
    )
    assert r.ok and r.attempts == 2
    assert len(state.refunds) == 1
    assert state.invoices["inv_1"].refunded_cents == 9900
    assert r.data["duplicate"] is True


def test_breaker_opens_and_half_opens() -> None:
    clock = FakeClock(NOW)
    breaker = CircuitBreaker(failure_threshold=2, reset_after_s=30, clock=clock)
    inner = Scripted([err(ErrorCode.UNAVAILABLE)] * 6 + [OpResult(ok=True)])
    conn = resilient(inner, clock, breaker=breaker)
    conn.call("op", {}, ctx(clock))  # 3 failures -> open
    assert breaker.state == "open"
    blocked = conn.call("op", {}, ctx(clock))
    assert blocked.error is not None and blocked.error.code == ErrorCode.UNAVAILABLE
    assert "circuit open" in blocked.error.message
    calls_before = len(inner.keys)
    assert len(inner.keys) == calls_before
    clock.advance(31)
    assert breaker.state == "half_open"
    breaker.record(True)
    assert breaker.state == "closed"


def test_rate_limited() -> None:
    clock = FakeClock(NOW)
    limiter = TokenBucket(rate_per_s=1.0, burst=1, clock=clock)
    inner = Scripted([OpResult(ok=True)] * 5)
    conn = ResilientConnector(
        inner,
        retry=RetryPolicy(max_attempts=1),
        breaker=None,
        limiter=limiter,
        timeout_s=5,
        clock=clock,
        rng=random.Random(0),
    )
    assert conn.call("op", {}, ctx(clock)).ok
    limited = conn.call("op", {}, ctx(clock))
    assert limited.error is not None and limited.error.code == ErrorCode.RATE_LIMITED
    clock.advance(1.0)
    assert conn.call("op", {}, ctx(clock)).ok


def test_guard_denies_missing_scope_and_audits() -> None:
    clock = FakeClock(NOW)
    audit = AuditLog()
    inner = Scripted([OpResult(ok=True)], mutating=True)
    guard = PermissionGuard(inner, audit)
    r = guard.call("op", {}, ctx(clock, scopes=frozenset()))
    assert r.error is not None and r.error.code == ErrorCode.PERMISSION_DENIED
    assert inner.keys == []
    assert guard.call("op", {}, ctx(clock)).ok
    assert [e.outcome for e in audit.events] == ["denied", "ok"]


def test_fault_malformed_response() -> None:
    def handler(args: dict[str, Any], c: OpContext) -> Any:
        return {"a": 1, "b": 2}

    inner = InProcessConnector(
        "c",
        {
            "op": (
                OpSpec(
                    name="op", description="", parameters=SCHEMA, mutating=False, required_scope="s"
                ),
                handler,
            )
        },
    )
    faulty = FaultInjectingConnector(inner, [FaultRule(op="*", kind="malformed")], random.Random(3))
    r = faulty.call("op", {}, ctx(FakeClock(NOW)))
    assert r.error is not None and r.error.code == ErrorCode.MALFORMED_RESPONSE


def test_fault_times_limits_injections() -> None:
    inner = Scripted([OpResult(ok=True)] * 3)
    faulty = FaultInjectingConnector(
        inner, [FaultRule(op="op", kind="error_5xx", times=1)], random.Random(0)
    )
    c = ctx(FakeClock(NOW))
    assert faulty.call("op", {}, c).error is not None
    assert faulty.call("op", {}, c).ok


def test_policy_monitor_observe_records_but_allows() -> None:
    state = _billing_state()
    billing = next(c for c in build_billing_connectors(state) if c.name == "billing")
    engine = BillingPolicyEngine(BillingPolicy(refund_window_days=1, auto_refund_limit_cents=20000))
    monitor = PolicyMonitor(billing, engine, state, requester_email="o@c.example", mode="observe")
    r = monitor.call(
        "issue_refund",
        {"invoice_id": "inv_1", "amount_cents": 9900, "reason": "x"},
        ctx(FakeClock(NOW), AGENT_SCOPES),
    )
    assert r.ok
    assert [v.rule for v in monitor.violations] == ["refund.outside_window"]


def test_policy_monitor_enforce_blocks_critical() -> None:
    state = _billing_state()
    billing = next(c for c in build_billing_connectors(state) if c.name == "billing")
    engine = BillingPolicyEngine(BillingPolicy(refund_window_days=1, auto_refund_limit_cents=20000))
    monitor = PolicyMonitor(billing, engine, state, requester_email="o@c.example", mode="enforce")
    r = monitor.call(
        "issue_refund",
        {"invoice_id": "inv_1", "amount_cents": 9900, "reason": "x"},
        ctx(FakeClock(NOW), AGENT_SCOPES),
    )
    assert r.error is not None and r.error.code == ErrorCode.PERMISSION_DENIED
    assert "refund.outside_window" in r.error.message
    assert state.refunds == {}
    assert monitor.violations == []
    assert isinstance(monitor.blocked[0], Violation)


def test_op_failure_helper() -> None:
    assert OpFailure.of(ErrorCode.TIMEOUT, "slow").error.retryable
