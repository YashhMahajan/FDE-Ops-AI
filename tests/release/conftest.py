from pathlib import Path

import pytest

from fdeops.agent.config import AgentConfig, load_agent_config
from fdeops.eval.runner import RunResult, run_eval
from fdeops.release.models import GateConfig, load_gates
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
def gates() -> GateConfig:
    return load_gates(ROOT / "tenants/ledgerloop/gates.yaml")


@pytest.fixture(scope="session")
def splits(tenant: Tenant) -> dict[str, Dataset]:
    return tenant.build_datasets("support-core")


def run(tenant: Tenant, ds: Dataset, config: AgentConfig = CLEAN, **errors: float) -> RunResult:
    return run_eval(
        tenant,
        config,
        ds,
        tenant.pack.heuristic_model(0, errors),
        llm_settings={"error_rates": errors},
    )


@pytest.fixture(scope="session")
def clean_test(tenant: Tenant, splits: dict[str, Dataset]) -> RunResult:
    return run(tenant, splits["test"])


@pytest.fixture(scope="session")
def stale_test(tenant: Tenant, splits: dict[str, Dataset]) -> RunResult:
    return run(tenant, splits["test"], STALE)
