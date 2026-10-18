from fdeops.packs.billing.entities import (
    Customer,
    ExportRequest,
    Invoice,
    Plan,
    PlanChange,
    Refund,
    Ticket,
    User,
)
from fdeops.world.state import WorldState


class BillingState(WorldState):
    plans: dict[str, Plan] = {}
    customers: dict[str, Customer] = {}
    users: dict[str, User] = {}
    invoices: dict[str, Invoice] = {}
    refunds: dict[str, Refund] = {}
    plan_changes: dict[str, PlanChange] = {}
    export_requests: dict[str, ExportRequest] = {}
    tickets: dict[str, Ticket] = {}

    def user_by_email(self, email: str) -> User | None:
        needle = email.strip().lower()
        for u in self.users.values():
            if u.email.lower() == needle:
                return u
        return None
