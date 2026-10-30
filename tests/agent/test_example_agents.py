from pathlib import Path

from fdeops.agent.config import AgentConfig, ModelRef
from fdeops.cli.common import load_external_agent
from fdeops.eval.runner import run_eval
from fdeops.tenancy.loader import Tenant

ROOT = Path(__file__).parents[2]
CFG = AgentConfig(id="external", model=ModelRef(provider="external", name="example"))
REFUND = ("refund_eligible", "refund_outside_window", "refund_over_limit")


def _run(tenant: Tenant, example: str):  # type: ignore[no-untyped-def]
    ds = tenant.build_datasets("support-core")["dev"]
    refunds = ds.model_copy(update={"cases": tuple(c for c in ds.cases if c.scenario in REFUND)})
    agent = load_external_agent(str(ROOT / "examples" / "agents" / f"{example}.py:agent"))
    return run_eval(tenant, CFG, refunds, None, external_agent=agent)


def test_careful_refunder_obeys_the_policy_and_beats_the_naive_agent(tenant: Tenant) -> None:
    careful, naive = _run(tenant, "careful_refunder"), _run(tenant, "naive_refunder")
    assert careful.results and not [r for r in careful.results if r.episode.violations]
    assert all(r.success for r in careful.results)
    assert sum(r.success for r in naive.results) < len(naive.results)
