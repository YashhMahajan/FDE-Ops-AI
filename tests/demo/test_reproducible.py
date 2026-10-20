"""The documents claim: the same seed gives the same numbers. This test makes sure of it."""

from pathlib import Path

from fdeops.agent.config import load_agent_config
from fdeops.eval.incidents import load_incident
from fdeops.eval.report import summarize
from fdeops.eval.runner import run_eval
from fdeops.tenancy.loader import load_tenant

ROOT = Path(__file__).parents[2]


def test_two_runs_give_the_same_numbers() -> None:
    t = load_tenant(ROOT / "tenants/ledgerloop")
    c = load_agent_config(ROOT / "configs/agents/ledgerloop-heuristic.yaml")
    ds = t.build_datasets("support-core")["test"]
    inc = load_incident(ROOT / "incidents/ledgerloop/refund-window-drift.yaml")
    a, b = (
        summarize(run_eval(t, c, ds, t.pack.heuristic_model(0, {}), incident=inc)) for _ in range(2)
    )
    assert a.metrics == b.metrics  # latency, tokens and retrieval values are equal
    assert a.overall == b.overall and a.by_scenario == b.by_scenario
