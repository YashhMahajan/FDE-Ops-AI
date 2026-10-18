import random
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fdeops.retrieval.kb import KnowledgeBase
from fdeops.world.cases import (
    CaseDraft,
    Expected,
    Fact,
    Resolution,
    TicketInput,
)
from fdeops.world.dataset import DatasetSpec, build_datasets, load_dataset, save_dataset
from fdeops.world.scenario import ScenarioContext
from fdeops.world.state import WorldState

from fdeops.core.errors import ConfigError

NOW = datetime(2026, 9, 15, 12, tzinfo=UTC)


class ToyScenario:
    id = "toy"

    def generate(self, ctx: ScenarioContext) -> CaseDraft:
        n = ctx.rng.randint(1, 10_000)
        return CaseDraft(
            tenant_id=ctx.tenant_id,
            scenario=self.id,
            now=ctx.now,
            ticket=TicketInput(
                ticket_id=f"tkt_{ctx.variant}",
                subject="hello",
                body=f"number {n}",
                requester_email="a@b.example",
            ),
            fixtures={},
            hidden_facts={},
            expected=Expected(resolution=Resolution.INFORMED),
            tags=("toy",),
            difficulty="easy",
        )


def spec(seed: int = 7) -> DatasetSpec:
    return DatasetSpec(name="core", version=1, seed=seed, cases_per_scenario={"toy": 40}, now=NOW)


def build(seed: int = 7):  # type: ignore[no-untyped-def]
    return build_datasets(
        tenant_id="t1",
        spec=spec(seed),
        scenarios={"toy": ToyScenario()},
        base_world=WorldState(),
        policy=None,
        kb=KnowledgeBase(()),
        generator_version="test-1",
    )


def test_build_is_deterministic() -> None:
    a, b = build(), build()
    assert a["dev"].content_hash == b["dev"].content_hash
    assert a["test"].content_hash == b["test"].content_hash


def test_different_seed_changes_hash() -> None:
    assert build(7)["test"].content_hash != build(8)["test"].content_hash


def test_split_is_disjoint_and_stable() -> None:
    ds = build()
    dev_ids = {c.id for c in ds["dev"].cases}
    test_ids = {c.id for c in ds["test"].cases}
    assert dev_ids.isdisjoint(test_ids)
    assert len(dev_ids) + len(test_ids) == 40
    assert 0.3 < len(test_ids) / 40 < 0.9
    assert all(c.split == "test" for c in ds["test"].cases)
    # split membership depends on case id only, not on seed
    other = build(8)
    assert {c.id for c in other["test"].cases} == test_ids


def test_case_provenance_recorded() -> None:
    case = build()["test"].cases[0]
    assert case.provenance.generator_version == "test-1"
    assert case.provenance.scenario == "toy"
    assert case.provenance.seed == 7


def test_save_load_roundtrip_and_tamper_detected(tmp_path: Path) -> None:
    ds = build()["test"]
    path = save_dataset(ds, tmp_path)
    assert (path / "manifest.json").exists()
    loaded = load_dataset(path, "test")
    assert loaded.content_hash == ds.content_hash
    jsonl = path / "test.jsonl"
    jsonl.write_text(jsonl.read_text().replace("number", "NUMBER", 1))
    with pytest.raises(ConfigError):
        load_dataset(path, "test")


def test_fact_present_in() -> None:
    f = Fact(id="window", description="14 day window", patterns=(r"\b14[- ]day", r"two weeks"))
    assert f.present_in("You have a 14-day window")
    assert f.present_in("within TWO WEEKS of payment")
    assert not f.present_in("30 days")


def test_rng_isolated_per_case() -> None:
    # adding a scenario must not change existing cases (per-case RNG seeding)
    ds1 = build()["test"]
    rng_state = random.getstate()
    ds2 = build()["test"]
    assert random.getstate() == rng_state
    assert ds1.cases == ds2.cases
