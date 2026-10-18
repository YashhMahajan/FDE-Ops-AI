from datetime import UTC, datetime

import pytest

from fdeops.packs.billing.entities import Plan
from fdeops.packs.billing.generator import BillingWorldSpec, generate_base_world
from fdeops.packs.billing.policy import BillingPolicy
from fdeops.packs.billing.state import BillingState

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)

PLANS = [
    Plan(id="plan_starter", name="Starter", tier=1, monthly_price_cents=2900),
    Plan(id="plan_growth", name="Growth", tier=2, monthly_price_cents=9900),
    Plan(id="plan_scale", name="Scale", tier=3, monthly_price_cents=29900),
    Plan(id="plan_enterprise", name="Enterprise", tier=4, monthly_price_cents=89900),
]


@pytest.fixture
def spec() -> BillingWorldSpec:
    return BillingWorldSpec(n_customers=30, seed=11, plans=PLANS)


@pytest.fixture
def world(spec: BillingWorldSpec) -> BillingState:
    return generate_base_world(spec, NOW)


@pytest.fixture
def policy() -> BillingPolicy:
    return BillingPolicy(refund_window_days=14, auto_refund_limit_cents=20000)
