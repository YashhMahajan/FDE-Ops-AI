from datetime import date, datetime
from typing import Literal

from fdeops.packs.common.tickets import Ticket
from fdeops.world.state import Entity

__all__ = ["Account", "AddressChange", "Claim", "Shipment", "ShipmentStatus", "Ticket", "User"]


class Account(Entity):
    company: str
    tier: Literal["standard", "priority"]
    created_at: datetime


class User(Entity):
    account_id: str
    email: str
    name: str
    role: Literal["owner", "admin", "member"]


ShipmentStatus = Literal[
    "label_created", "in_transit", "out_for_delivery", "delivered", "delayed", "lost"
]


class Shipment(Entity):
    account_id: str
    tracking_number: str
    status: ShipmentStatus
    origin_city: str
    destination_address: str
    recipient_name: str
    recipient_phone: str
    declared_value_cents: int
    shipped_at: datetime
    eta: date
    delivered_at: datetime | None = None


class Claim(Entity):
    shipment_id: str
    kind: Literal["damage", "loss"]
    amount_cents: int
    description: str
    status: Literal["approved"]
    created_at: datetime
    idempotency_key: str | None = None


class AddressChange(Entity):
    shipment_id: str
    new_address: str
    created_at: datetime
