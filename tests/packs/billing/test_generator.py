from fdeops.core.hashing import content_hash
from fdeops.packs.billing.generator import BillingWorldSpec, generate_base_world
from fdeops.packs.billing.state import BillingState

from .conftest import NOW


def test_world_deterministic(spec: BillingWorldSpec) -> None:
    assert content_hash(generate_base_world(spec, NOW)) == content_hash(
        generate_base_world(spec, NOW)
    )
    # A different seed gives a different world: the hash is not a constant.
    other = spec.model_copy(update={"seed": spec.seed + 1})
    assert content_hash(generate_base_world(other, NOW)) != content_hash(
        generate_base_world(spec, NOW)
    )


def test_seed_changes_world(spec: BillingWorldSpec) -> None:
    other = spec.model_copy(update={"seed": 12})
    assert content_hash(generate_base_world(spec, NOW)) != content_hash(
        generate_base_world(other, NOW)
    )


def test_emails_unique_and_reserved_tld(world: BillingState) -> None:
    emails = [u.email for u in world.users.values()]
    assert len(emails) == len(set(emails))
    assert all(e.endswith(".example") for e in emails)


def test_every_customer_has_owner(world: BillingState) -> None:
    assert len(world.customers) == 30
    for cid in world.customers:
        assert any(u.customer_id == cid and u.role == "owner" for u in world.users.values())


def test_invoices_reference_customers_and_are_in_past(world: BillingState) -> None:
    assert world.invoices
    for inv in world.invoices.values():
        assert inv.customer_id in world.customers
        assert inv.issued_at <= NOW
        if inv.status == "paid":
            assert inv.paid_at is not None and inv.paid_at <= NOW
