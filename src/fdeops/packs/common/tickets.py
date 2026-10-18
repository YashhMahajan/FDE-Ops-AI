"""Ticket entities and the three terminal operations that end an agent turn.

Each domain pack has a ``tickets`` collection of ``Ticket`` entities and uses these operations.
"""

from datetime import datetime
from typing import Any, Literal

from fdeops.connectors.base import Handler, InProcessConnector, OpContext, OpSpec
from fdeops.core.model import FrozenModel
from fdeops.packs.common.schema import ID, TEXT, not_found, obj, spec
from fdeops.world.cases import TicketInput
from fdeops.world.state import Entity, WorldState


class Reply(FrozenModel):
    author: Literal["agent", "customer"]
    message: str
    at: datetime


class Escalation(FrozenModel):
    reason_code: str
    note: str
    at: datetime


TicketStatus = Literal["open", "pending_customer", "escalated", "solved"]


class Ticket(Entity):
    customer_id: str | None
    requester_email: str
    subject: str
    body: str
    status: TicketStatus
    created_at: datetime
    replies: tuple[Reply, ...] = ()
    escalation: Escalation | None = None


def _tickets(state: WorldState) -> dict[str, Ticket]:
    return state.collection("tickets")  # type: ignore[return-value]


def build_ticketing_connector(state: WorldState) -> InProcessConnector:
    def get(ticket_id: str) -> Ticket:
        t = _tickets(state).get(ticket_id)
        if t is None:
            raise not_found("ticket")
        return t

    def reply_to_customer(args: dict[str, Any], ctx: OpContext) -> Any:
        t = get(args["ticket_id"])
        reply = Reply(author="agent", message=args["message"], at=ctx.clock.now())
        state.upsert(
            "tickets", t.model_copy(update={"replies": (*t.replies, reply), "status": "solved"})
        )
        return {"ticket_id": t.id, "status": "solved"}

    def ask_clarifying_question(args: dict[str, Any], ctx: OpContext) -> Any:
        t = get(args["ticket_id"])
        reply = Reply(author="agent", message=args["question"], at=ctx.clock.now())
        state.upsert(
            "tickets",
            t.model_copy(update={"replies": (*t.replies, reply), "status": "pending_customer"}),
        )
        return {"ticket_id": t.id, "status": "pending_customer"}

    def escalate_to_human(args: dict[str, Any], ctx: OpContext) -> Any:
        t = get(args["ticket_id"])
        esc = Escalation(reason_code=args["reason_code"], note=args["note"], at=ctx.clock.now())
        state.upsert("tickets", t.model_copy(update={"escalation": esc, "status": "escalated"}))
        return {"ticket_id": t.id, "status": "escalated"}

    ops: dict[str, tuple[OpSpec, Handler]] = {
        "reply_to_customer": (
            spec(
                "reply_to_customer",
                "Send the last reply to the customer and close the ticket.",
                obj({"ticket_id": ID, "message": TEXT}, ["ticket_id", "message"]),
                "tickets:write",
                mutating=True,
                terminal="reply",
            ),
            reply_to_customer,
        ),
        "ask_clarifying_question": (
            spec(
                "ask_clarifying_question",
                "Send a question to the customer and wait for the answer.",
                obj({"ticket_id": ID, "question": TEXT}, ["ticket_id", "question"]),
                "tickets:write",
                mutating=True,
                terminal="clarify",
            ),
            ask_clarifying_question,
        ),
        "escalate_to_human": (
            spec(
                "escalate_to_human",
                "Send the ticket to a human specialist with a reason code.",
                obj(
                    {"ticket_id": ID, "reason_code": ID, "note": TEXT},
                    ["ticket_id", "reason_code", "note"],
                ),
                "tickets:escalate",
                mutating=True,
                terminal="escalate",
            ),
            escalate_to_human,
        ),
    }
    return InProcessConnector("ticketing", ops)


def open_ticket(state: WorldState, ticket: TicketInput, now: datetime) -> None:
    state.upsert(
        "tickets",
        Ticket(
            id=ticket.ticket_id,
            customer_id=None,
            requester_email=ticket.requester_email,
            subject=ticket.subject,
            body=ticket.body,
            status="open",
            created_at=now,
        ),
    )


def add_customer_reply(state: WorldState, ticket_id: str, message: str, now: datetime) -> None:
    t = _tickets(state)[ticket_id]
    reply = Reply(author="customer", message=message, at=now)
    state.upsert("tickets", t.model_copy(update={"replies": (*t.replies, reply), "status": "open"}))


def agent_messages(state: WorldState, ticket_id: str) -> list[str]:
    """Customer-facing text only. Escalation notes are internal."""
    t = _tickets(state).get(ticket_id)
    return [r.message for r in t.replies if r.author == "agent"] if t else []


TICKET_OPS = frozenset({"reply_to_customer", "ask_clarifying_question", "escalate_to_human"})
