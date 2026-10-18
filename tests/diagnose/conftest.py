from collections.abc import Sequence
from pathlib import Path

import pytest

from fdeops.agent.config import AgentConfig, load_agent_config
from fdeops.connectors.faults import FaultRule
from fdeops.eval.runner import RunResult, run_eval
from fdeops.retrieval.retriever import RetrievalConfig
from fdeops.tenancy.loader import Tenant, load_tenant
from fdeops.world.dataset import Dataset

ROOT = Path(__file__).parents[2]
CLEAN = load_agent_config(ROOT / "configs/agents/ledgerloop-heuristic.yaml")
STALE = CLEAN.model_copy(
    update={"id": "stale", "retrieval": RetrievalConfig(include_superseded=True)}
)


@pytest.fixture(scope="session")
def tenant() -> Tenant:
    return load_tenant(ROOT / "tenants/ledgerloop")


@pytest.fixture(scope="session")
def dev(tenant: Tenant) -> Dataset:
    return tenant.build_datasets("support-core")["dev"]


def subset(ds: Dataset, *scenarios: str, tag: str | None = None) -> Dataset:
    cases = tuple(c for c in ds.cases if c.scenario in scenarios or (tag and tag in c.tags))
    return ds.model_copy(update={"cases": cases})


def run(
    tenant: Tenant,
    ds: Dataset,
    config: AgentConfig = CLEAN,
    trials: int = 1,
    faults: Sequence[FaultRule] = (),
    **errors: float,
) -> RunResult:
    return run_eval(
        tenant,
        config,
        ds,
        tenant.pack.heuristic_model(0, errors),
        trials=trials,
        faults=faults,
        llm_settings={"error_rates": errors},
    )
