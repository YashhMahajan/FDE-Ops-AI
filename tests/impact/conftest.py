from pathlib import Path

import pytest

from fdeops.agent.config import load_agent_config
from fdeops.eval.runner import RunResult, run_eval
from fdeops.impact.costs import CostModel, load_costs
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
def costs() -> CostModel:
    return load_costs(ROOT / "tenants/ledgerloop/costs.yaml")


@pytest.fixture(scope="session")
def dev(tenant: Tenant) -> Dataset:
    return tenant.build_datasets("support-core")["dev"]


@pytest.fixture(scope="session")
def clean_dev(tenant: Tenant, dev: Dataset) -> RunResult:
    return run_eval(tenant, CLEAN, dev, tenant.pack.heuristic_model(0, {}))


@pytest.fixture(scope="session")
def stale_dev(tenant: Tenant, dev: Dataset) -> RunResult:
    return run_eval(tenant, STALE, dev, tenant.pack.heuristic_model(0, {}))
