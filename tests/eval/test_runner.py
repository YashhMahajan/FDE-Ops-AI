import json
from pathlib import Path

import pytest

from fdeops.agent.config import AgentConfig, ModelRef, load_agent_config
from fdeops.core.errors import ConfigError
from fdeops.core.provenance import Provenance
from fdeops.eval.compare import compare_runs, render_comparison
from fdeops.eval.report import load_run, render_markdown, save_run, summarize
from fdeops.eval.runner import run_eval
from fdeops.llm.scripted import ScriptedLLM
from fdeops.retrieval.retriever import RetrievalConfig
from fdeops.tenancy.loader import Tenant
from fdeops.world.dataset import Dataset

ROOT = Path(__file__).parents[2]
GOLDEN = ROOT / "tests" / "golden" / "heuristic_run_summary.json"
CFG = load_agent_config(ROOT / "configs" / "agents" / "ledgerloop-heuristic.yaml")


@pytest.fixture(scope="module")
def test_split(tenant: Tenant) -> Dataset:
    return tenant.build_datasets("support-core")["test"]


@pytest.fixture(scope="module")
def clean_run(tenant: Tenant, test_split: Dataset):  # type: ignore[no-untyped-def]
    return run_eval(tenant, CFG, test_split, tenant.pack.heuristic_model(0, {}), trials=2)


def test_run_eval_heuristic_produces_pipeline_test_provenance(clean_run) -> None:  # type: ignore[no-untyped-def]
    assert clean_run.provenance == Provenance.PIPELINE_TEST
    assert len(clean_run.results) == 2 * len({r.case_id for r in clean_run.results})
    assert clean_run.agent_config_hash == CFG.content_hash


def test_results_ordered_and_scored(clean_run, test_split: Dataset) -> None:  # type: ignore[no-untyped-def]
    ids = [(r.case_id, r.trial) for r in clean_run.results]
    assert ids == [(c.id, t) for c in test_split.cases for t in range(2)]
    assert all(any(s.name == "outcome" for s in r.scores) for r in clean_run.results)


def test_summary_and_markdown(clean_run) -> None:  # type: ignore[no-untyped-def]
    s = summarize(clean_run)
    assert s.overall.n == len(clean_run.results)
    assert 0 <= s.overall.ci_lo <= s.overall.rate <= s.overall.ci_hi <= 1
    assert set(s.pass_hat_k) == {"1", "2"}
    assert s.pass_hat_k["2"] <= s.pass_hat_k["1"]
    assert {x.slice for x in s.by_scenario} >= {"refund_eligible", "injection_refund"}
    md = render_markdown(s)
    assert md.splitlines()[0].startswith("> **Provenance: pipeline-test**")
    assert "| refund_eligible |" in md


def test_summary_matches_golden(clean_run) -> None:  # type: ignore[no-untyped-def]
    s = summarize(clean_run)
    stable = {
        "overall": [s.overall.n, s.overall.successes],
        "by_scenario": {x.slice: [x.n, x.successes] for x in s.by_scenario},
        "critical_violations": s.critical_violations,
    }
    assert stable == json.loads(GOLDEN.read_text())


def test_save_and_load_roundtrip(clean_run, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    path = save_run(clean_run, tmp_path)
    assert (path / "report.md").exists() and (path / "summary.json").exists()
    assert load_run(path) == clean_run


def test_compare_detects_injected_regression(
    tenant: Tenant, test_split: Dataset, clean_run
) -> None:  # type: ignore[no-untyped-def]
    buggy = run_eval(
        tenant,
        CFG,
        test_split,
        tenant.pack.heuristic_model(0, {"wrong_amount": 0.7, "miss_escalation": 0.7}),
        trials=2,
    )
    cmp = compare_runs(clean_run, buggy)
    assert cmp.diff.mean < 0 and cmp.diff.hi < 0
    assert cmp.mcnemar_p < 0.05
    assert cmp.by_scenario["refund_eligible"].mean < 0
    assert set(cmp.holm_p) == set(cmp.by_scenario)
    assert "Regression: B is worse than A" in render_comparison(cmp)


def test_stale_index_regression_is_localized(
    tenant: Tenant, test_split: Dataset, clean_run
) -> None:  # type: ignore[no-untyped-def]
    stale_cfg = CFG.model_copy(update={"retrieval": RetrievalConfig(include_superseded=True)})
    stale = run_eval(tenant, stale_cfg, test_split, tenant.pack.heuristic_model(0, {}), trials=2)
    cmp = compare_runs(clean_run, stale)
    assert cmp.by_scenario["refund_outside_window"].mean < 0
    assert cmp.by_scenario["export_authorized"].mean == 0
    assert summarize(stale).metrics["stale_hit_rate"] > 0


def test_compare_rejects_different_datasets(tenant: Tenant, clean_run) -> None:  # type: ignore[no-untyped-def]
    dev = tenant.build_datasets("support-core")["dev"]
    other = run_eval(tenant, CFG, dev, tenant.pack.heuristic_model(0, {}), trials=1)
    with pytest.raises(ConfigError):
        compare_runs(clean_run, other)


def test_dataset_must_match_tenant_world(tenant: Tenant, test_split: Dataset) -> None:
    tampered = test_split.model_copy(update={"kb_hash": "sha256:" + "0" * 64})
    with pytest.raises(ConfigError):
        run_eval(tenant, CFG, tampered, tenant.pack.heuristic_model(0, {}))


def test_real_model_provenance(tenant: Tenant, test_split: Dataset) -> None:
    class Fake(ScriptedLLM):
        provider = "openrouter"

    one = test_split.model_copy(update={"cases": test_split.cases[:1]})
    llm = Fake(lambda r: "no tools")
    cfg = AgentConfig(id="x", model=ModelRef(provider="openrouter", name="m"), max_steps=2)
    run = run_eval(tenant, cfg, one, llm)
    assert run.provenance == Provenance.MEASURED_IN_SIMULATION


def test_compare_pairs_at_case_level_not_trial_level(
    tenant: Tenant, test_split: Dataset, clean_run
) -> None:  # type: ignore[no-untyped-def]
    # Two trials of a deterministic model are perfectly correlated: evidence must not double.
    buggy = run_eval(
        tenant, CFG, test_split, tenant.pack.heuristic_model(0, {"wrong_amount": 1.0}), trials=2
    )
    cmp = compare_runs(clean_run, buggy)
    assert cmp.n_pairs == len(test_split.cases)
    assert cmp.trials == 2
    assert cmp.a_only + cmp.b_only <= len(test_split.cases)


def test_summary_reports_minimum_detectable_effect(clean_run) -> None:  # type: ignore[no-untyped-def]
    s = summarize(clean_run)
    assert 0 < s.metrics["mde"] < 1
    assert "minimum change that a test can find" in render_markdown(s)


def test_compare_reports_tags(tenant: Tenant, test_split: Dataset, clean_run) -> None:  # type: ignore[no-untyped-def]
    stale_cfg = CFG.model_copy(update={"retrieval": RetrievalConfig(include_superseded=True)})
    stale = run_eval(tenant, stale_cfg, test_split, tenant.pack.heuristic_model(0, {}), trials=2)
    cmp = compare_runs(clean_run, stale)
    assert cmp.by_tag["drift_sensitive"].mean < 0
    assert set(cmp.tag_holm_p) == set(cmp.by_tag)
    assert "Results for each tag" in render_comparison(cmp)
