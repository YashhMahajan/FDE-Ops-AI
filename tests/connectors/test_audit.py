from datetime import UTC, datetime

from fdeops.connectors.audit import AuditLog

NOW = datetime(2026, 9, 15, tzinfo=UTC)


def test_chain_verifies() -> None:
    log = AuditLog()
    for i in range(5):
        log.append(
            at=NOW,
            tenant_id="t",
            actor="agent",
            action="call",
            op=f"op{i}",
            args={"i": i},
            outcome="ok",
        )
    assert log.verify() is None
    assert log.events[1].prev_hash == log.events[0].hash
    assert log.events[0].seq == 0


def test_audit_tamper_detected() -> None:
    log = AuditLog()
    for i in range(4):
        log.append(
            at=NOW,
            tenant_id="t",
            actor="agent",
            action="call",
            op="op",
            args={"i": i},
            outcome="ok",
        )
    log._events[2] = log.events[2].model_copy(update={"outcome": "denied"})
    assert log.verify() == 2


def test_args_are_hashed_not_stored() -> None:
    log = AuditLog()
    e = log.append(
        at=NOW,
        tenant_id="t",
        actor="agent",
        action="call",
        op="lookup",
        args={"email": "secret@x.example"},
        outcome="ok",
    )
    assert "secret" not in e.model_dump_json()
