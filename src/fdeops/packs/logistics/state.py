from fdeops.packs.logistics.entities import (
    Account,
    AddressChange,
    Claim,
    Shipment,
    Ticket,
    User,
)
from fdeops.world.state import WorldState


class LogisticsState(WorldState):
    accounts: dict[str, Account] = {}
    users: dict[str, User] = {}
    shipments: dict[str, Shipment] = {}
    claims: dict[str, Claim] = {}
    address_changes: dict[str, AddressChange] = {}
    tickets: dict[str, Ticket] = {}

    def user_by_email(self, email: str) -> User | None:
        needle = email.strip().lower()
        return next((u for u in self.users.values() if u.email.lower() == needle), None)

    def shipment_by_tracking(self, tracking: str) -> Shipment | None:
        needle = tracking.strip().upper()
        return next((s for s in self.shipments.values() if s.tracking_number == needle), None)
