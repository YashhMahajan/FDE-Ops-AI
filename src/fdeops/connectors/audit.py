"""Append-only, hash-chained audit log. Each event commits to the previous event's hash, so editing
or deleting any past event is detectable. Arguments are stored as a hash only, never in clear, so
the log itself does not become a store of customer PII."""

from datetime import datetime
from typing import Any

from fdeops.core.hashing import content_hash
from fdeops.core.model import FrozenModel

GENESIS = "sha256:" + "0" * 64


class AuditEvent(FrozenModel):
    seq: int
    at: datetime
    tenant_id: str
    actor: str
    action: str
    op: str
    args_hash: str
    outcome: str
    prev_hash: str
    hash: str


def _event_hash(fields: dict[str, Any]) -> str:
    return content_hash({k: v for k, v in fields.items() if k != "hash"})


class AuditLog:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    @property
    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

    def append(
        self,
        *,
        at: datetime,
        tenant_id: str,
        actor: str,
        action: str,
        op: str,
        args: Any,
        outcome: str,
    ) -> AuditEvent:
        fields: dict[str, Any] = {
            "seq": len(self._events),
            "at": at,
            "tenant_id": tenant_id,
            "actor": actor,
            "action": action,
            "op": op,
            "args_hash": content_hash(args),
            "outcome": outcome,
            "prev_hash": self._events[-1].hash if self._events else GENESIS,
        }
        event = AuditEvent(**fields, hash=_event_hash(fields))
        self._events.append(event)
        return event

    def verify(self) -> int | None:
        """Index of the first event whose hash or link is wrong, or ``None`` if the chain holds."""
        prev = GENESIS
        for i, e in enumerate(self._events):
            if e.prev_hash != prev or e.hash != _event_hash(e.model_dump()):
                return i
            prev = e.hash
        return None
