from datetime import date, datetime
from typing import Literal

from fdeops.packs.common.tickets import Escalation, Reply, Ticket, TicketStatus
from fdeops.world.state import Entity

__all__ = [
    "Customer",
    "Escalation",
    "ExportRequest",
    "Invoice",
    "Plan",
    "Refund",
    "Reply",
    "Ticket",
    "TicketStatus",
    "User",
    "format_money",
]


class Plan(Entity):
    name: str
    tier: int
    monthly_price_cents: int


class Customer(Entity):
    company: str
    plan_id: str
    status: Literal["active", "past_due", "cancelled"]
    created_at: datetime


class User(Entity):
    customer_id: str
    email: str
    name: str
    role: Literal["owner", "admin", "member"]


InvoiceStatus = Literal["open", "paid", "failed", "refunded", "partially_refunded"]


class Invoice(Entity):
    customer_id: str
    amount_cents: int
    period_start: date
    period_end: date
    issued_at: datetime
    paid_at: datetime | None
    status: InvoiceStatus
    refunded_cents: int = 0
    description: str = "Subscription"

    @property
    def refundable_cents(self) -> int:
        return self.amount_cents - self.refunded_cents


class Refund(Entity):
    invoice_id: str
    amount_cents: int
    reason: str
    created_at: datetime
    idempotency_key: str | None = None


class ExportRequest(Entity):
    customer_id: str
    requested_by: str
    created_at: datetime


def format_money(cents: int) -> str:
    return f"${cents / 100:,.2f}"
