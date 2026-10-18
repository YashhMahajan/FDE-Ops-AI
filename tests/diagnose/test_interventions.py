import pytest

from fdeops.agent.config import apply_patch
from fdeops.core.errors import ConfigError
from fdeops.diagnose.classify import classify_run
from fdeops.diagnose.clusters import cluster_failures
from fdeops.diagnose.interventions import (
    PLAYBOOK,
    Verdict,
    candidates,
    diagnose_run,
)
from fdeops.diagnose.taxonomy import FailureClass
from fdeops.eval.report import load_run, save_run
from fdeops.tenancy.loader import Tenant
from fdeops.world.dataset import Dataset

from .conftest import CLEAN, STALE, run, subset


def heuristic(tenant: Tenant, errors: dict[str, float] | None = None):  # type: ignore[no-untyped-def]
    return tenant.pack.heuristic_model(0, errors or {})


def test_apply_patch_merges_nested_and_changes_hash() -> None:
    patched = apply_patch(STALE, {"retrieval": {"freshness_filter": True}})
    assert patched.retrieval.freshness_filter is True
    assert patched.retrieval.include_superseded is True
    assert patched.content_hash != STALE.content_hash
    with pytest.raises(ConfigError):
        apply_patch(STALE, {"retrieval": {"no_such_field": 1}})


def test_playbook_covers_actionable_classes() -> None:
    covered = {c for i in PLAYBOOK for c in i.applies_to}
    assert {
        FailureClass.STALE_KNOWLEDGE,
        FailureClass.RETRIEVAL_MISS,
        FailureClass.POLICY_VIOLATION,
        FailureClass.UNHANDLED_TOOL_ERROR,
        FailureClass.TIMEOUT_OR_BUDGET,
        FailureClass.INJECTION_FOLLOWED,
    } <= covered


def test_stale_cluster_confirmed_by_freshness_intervention(tenant: Tenant, dev: Dataset) -> None:
    ds = subset(
        dev,
        "refund_outside_window",
        "refund_eligible",
        "export_authorized",
        "payment_failed_help",
        "invoice_explain",
        "account_security",
        "plan_downgrade",
    )
    base = run(tenant, ds, config=STALE)
    diagnosis = diagnose_run(tenant, base, ds, heuristic(tenant))
    stale = next(
        d for d in diagnosis.clusters if d.cluster.failure_class == FailureClass.STALE_KNOWLEDGE
    )
    assert stale.verdict == Verdict.CONFIRMED
    ids = {r.intervention_id: r for r in stale.results}
    assert ids["freshness_filter"].fix_rate == 1.0
    assert ids["freshness_filter"].regressions == 0
    assert stale.recommended_fix in {"freshness_filter", "current_index_only"}


def test_regressions_block_confirmation(tenant: Tenant, dev: Dataset) -> None:
    from fdeops.diagnose.interventions import verdict_for

    assert verdict_for(n_cases=5, fix_ci=(0.6, 1.0), regression_ci=(0.3, 0.6)) != Verdict.CONFIRMED
    assert verdict_for(n_cases=5, fix_ci=(0.6, 1.0), regression_ci=(0.0, 0.1)) == Verdict.CONFIRMED


def test_small_cluster_is_inconclusive(tenant: Tenant, dev: Dataset) -> None:
    from fdeops.diagnose.interventions import verdict_for

    assert (
        verdict_for(n_cases=2, fix_ci=(0.9, 1.0), regression_ci=(0.0, 0.0)) == Verdict.INCONCLUSIVE
    )


def test_interventions_refuse_test_split(tenant: Tenant) -> None:
    test = tenant.build_datasets("support-core")["test"]
    ds = subset(test, "refund_outside_window")
    base = run(tenant, ds, config=STALE)
    with pytest.raises(ConfigError) as exc:
        diagnose_run(tenant, base, ds, heuristic(tenant))
    assert "dev" in str(exc.value)
    allowed = diagnose_run(tenant, base, ds, heuristic(tenant), allow_test=True)
    assert any("test split" in w for w in allowed.warnings)


def test_dataset_must_match_run(tenant: Tenant, dev: Dataset) -> None:
    base = run(tenant, subset(dev, "refund_eligible"), config=CLEAN)
    with pytest.raises(ConfigError):
        diagnose_run(tenant, base, subset(dev, "refund_outside_window"), heuristic(tenant))


def test_old_run_without_llm_settings_loads(tenant: Tenant, dev: Dataset, tmp_path) -> None:  # type: ignore[no-untyped-def]
    import json

    base = run(tenant, subset(dev, "refund_eligible"))
    path = save_run(base, tmp_path)
    raw = json.loads((path / "run.json").read_text())
    raw.pop("llm_settings")
    (path / "run.json").write_text(json.dumps(raw))
    assert load_run(path).llm_settings == {}


def test_candidates_for_cluster(tenant: Tenant, dev: Dataset) -> None:
    r = run(tenant, subset(dev, "refund_outside_window"), config=STALE)
    cluster = cluster_failures(classify_run(r, tenant.pack.knowledge_rules), r)[0]
    ids = [i.id for i in candidates(cluster)]
    assert "freshness_filter" in ids and "oracle_retrieval" in ids


def test_small_control_set_is_named_in_rationale(tenant: Tenant, dev: Dataset) -> None:
    ds = subset(dev, "refund_outside_window", "refund_eligible", "export_authorized")
    d = diagnose_run(tenant, run(tenant, ds, config=STALE), ds, heuristic(tenant))
    stale = next(c for c in d.clusters if c.cluster.failure_class == FailureClass.STALE_KNOWLEDGE)
    if stale.verdict != Verdict.CONFIRMED:
        assert "control cases" in stale.rationale
