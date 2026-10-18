"""Deterministic base world: background customers that make lookups realistic.

Scenario fixtures are added on top of this per case, with ids that can never collide with it
(fixture ids carry an ``x`` marker; base ids do not).
"""

import random
from datetime import datetime, timedelta

from fdeops.core.model import FrozenModel
from fdeops.packs.billing.entities import Customer, Invoice, Plan, User
from fdeops.packs.billing.state import BillingState

FIRST = [
    "ana",
    "ben",
    "chen",
    "dara",
    "eli",
    "fatima",
    "gus",
    "hana",
    "ivan",
    "jo",
    "kai",
    "lena",
    "mo",
    "nia",
    "omar",
    "pia",
    "raj",
    "sara",
    "tom",
    "uma",
    "vik",
    "wen",
    "yuki",
    "zoe",
]
LAST = [
    "adler",
    "bose",
    "cruz",
    "diaz",
    "eng",
    "fox",
    "gale",
    "haas",
    "iyer",
    "jung",
    "kerr",
    "lund",
    "moss",
    "nair",
    "ortiz",
    "park",
    "quinn",
    "roth",
    "shah",
    "tan",
    "ueda",
    "voss",
]
WORDS = [
    "acorn",
    "birch",
    "cobalt",
    "delta",
    "ember",
    "fjord",
    "granite",
    "harbor",
    "indigo",
    "juniper",
    "kestrel",
    "lumen",
    "meadow",
    "nimbus",
    "orchid",
    "pebble",
    "quartz",
    "ridge",
    "summit",
    "tundra",
    "umber",
    "vertex",
    "willow",
    "zephyr",
]
SUFFIX = ["labs", "works", "studio", "systems", "analytics", "co", "health", "logistics"]


class BillingWorldSpec(FrozenModel):
    n_customers: int = 40
    seed: int
    plans: list[Plan]
    history_months: int = 4


def _hex(rng: random.Random, bits: int = 32) -> str:
    return f"{rng.getrandbits(bits):0{bits // 4}x}"


def generate_base_world(spec: BillingWorldSpec, now: datetime) -> BillingState:
    rng = random.Random(spec.seed)
    state = BillingState()
    for plan in spec.plans:
        state.upsert("plans", plan)
    used_slugs: set[str] = set()
    for i in range(spec.n_customers):
        while True:
            slug = f"{rng.choice(WORDS)}-{rng.choice(SUFFIX)}"
            if slug not in used_slugs:
                used_slugs.add(slug)
                break
        plan = rng.choice(spec.plans)
        cid = f"cus_{i:03d}{_hex(rng, 16)}"
        created = now - timedelta(days=rng.randint(150, 900))
        status = "past_due" if rng.random() < 0.08 else "active"
        state.upsert(
            "customers",
            Customer(
                id=cid,
                company=slug.replace("-", " ").title(),
                plan_id=plan.id,
                status=status,
                created_at=created,
            ),
        )
        roles = ["owner", *rng.sample(["admin", "member", "member"], k=rng.randint(0, 2))]
        for j, role in enumerate(roles):
            first, last = rng.choice(FIRST), rng.choice(LAST)
            state.upsert(
                "users",
                User(
                    id=f"usr_{i:03d}{j}{_hex(rng, 16)}",
                    customer_id=cid,
                    email=f"{first}.{last}@{slug}.example",
                    name=f"{first.title()} {last.title()}",
                    role=role,
                ),
            )
        period_start = (now - timedelta(days=rng.randint(0, 27))).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        for m in range(spec.history_months):
            issued = period_start - timedelta(days=30 * m)
            failed = status == "past_due" and m == 0
            paid_at = None if failed else issued + timedelta(hours=rng.randint(0, 72))
            if paid_at is not None and paid_at > now:
                paid_at = now
            state.upsert(
                "invoices",
                Invoice(
                    id=f"inv_{i:03d}{m}{_hex(rng, 16)}",
                    customer_id=cid,
                    amount_cents=plan.monthly_price_cents,
                    period_start=issued.date(),
                    period_end=(issued + timedelta(days=30)).date(),
                    issued_at=issued,
                    paid_at=paid_at,
                    status="failed" if failed else "paid",
                ),
            )
    return state
