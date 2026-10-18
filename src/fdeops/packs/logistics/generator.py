"""Deterministic base world for a shipping SaaS: accounts, users and shipments."""

import random
from datetime import datetime, timedelta

from fdeops.core.model import FrozenModel
from fdeops.packs.billing.generator import FIRST, LAST, WORDS
from fdeops.packs.logistics.entities import Account, Shipment, User
from fdeops.packs.logistics.state import LogisticsState

CITIES = ["Rotterdam", "Lyon", "Porto", "Gdansk", "Leeds", "Bremen", "Turin", "Ghent"]
STREETS = ["Harbor Street", "Mill Road", "Station Road", "Canal Street", "Market Road"]


class LogisticsWorldSpec(FrozenModel):
    n_accounts: int = 40
    seed: int
    shipments_per_account: int = 3


def address(rng: random.Random) -> str:
    return f"{rng.randint(1, 240)} {rng.choice(STREETS)}, {rng.choice(CITIES)}"


def phone(rng: random.Random) -> str:
    return f"+31 6 {rng.randint(100, 999)} {rng.randint(1000, 9999)}"


def tracking(rng: random.Random) -> str:
    return f"PP{rng.randint(100_000_000, 999_999_999)}"


def generate_base_world(spec: LogisticsWorldSpec, now: datetime) -> LogisticsState:
    rng = random.Random(spec.seed)
    state = LogisticsState()
    used: set[str] = set()
    for i in range(spec.n_accounts):
        slug = f"{rng.choice(WORDS)}-{rng.choice(WORDS)}-{i:02d}"
        aid = f"acc_{i:03d}{rng.getrandbits(16):04x}"
        state.upsert(
            "accounts",
            Account(
                id=aid,
                company=slug.replace("-", " ").title(),
                tier=rng.choice(["standard", "priority"]),
                created_at=now - timedelta(days=rng.randint(100, 900)),
            ),
        )
        for j, role in enumerate(["owner", *rng.sample(["admin", "member"], rng.randint(0, 2))]):
            first, last = rng.choice(FIRST), rng.choice(LAST)
            state.upsert(
                "users",
                User(
                    id=f"usr_{i:03d}{j}{rng.getrandbits(16):04x}",
                    account_id=aid,
                    email=f"{first}.{last}@{slug}.example",
                    name=f"{first.title()} {last.title()}",
                    role=role,
                ),
            )
        for k in range(spec.shipments_per_account):
            while (tn := tracking(rng)) in used:
                pass
            used.add(tn)
            shipped = now - timedelta(days=rng.randint(1, 40), hours=rng.randint(0, 20))
            eta = (shipped + timedelta(days=rng.randint(2, 6))).date()
            delivered = eta < now.date() and rng.random() < 0.85
            status = "delivered" if delivered else rng.choice(["in_transit", "delayed"])
            state.upsert(
                "shipments",
                Shipment(
                    id=f"shp_{i:03d}{k}{rng.getrandbits(16):04x}",
                    account_id=aid,
                    tracking_number=tn,
                    status=status,
                    origin_city=rng.choice(CITIES),
                    destination_address=address(rng),
                    recipient_name=rng.choice(FIRST).title(),
                    recipient_phone=phone(rng),
                    declared_value_cents=100 * rng.randint(20, 2000),
                    shipped_at=shipped,
                    eta=eta,
                    delivered_at=datetime.combine(eta, shipped.timetz()) if delivered else None,
                ),
            )
    return state
