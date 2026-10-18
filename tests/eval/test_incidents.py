from pathlib import Path

import pytest

from fdeops.agent.config import load_agent_config
from fdeops.core.errors import ConfigError
from fdeops.eval.compare import compare_runs
from fdeops.eval.incidents import load_incident
from fdeops.eval.runner import run_eval
from fdeops.tenancy.loader import Tenant
from fdeops.world.dataset import Dataset

ROOT = Path(__file__).parents[2]
INC = ROOT / "incidents" / "ledgerloop"
CFG = load_agent_config(ROOT / "configs/agents/ledgerloop-heuristic.yaml")


@pytest.fixture(scope="module")
def dev(tenant: Tenant) -> Dataset:
    return tenant.build_datasets("support-core")["dev"]


def only(ds: Dataset, *scenarios: str) -> Dataset:
    return ds.model_copy(update={"cases": tuple(c for c in ds.cases if c.scenario in scenarios)})


def run(tenant: Tenant, ds: Dataset, name: str | None = None):  # type: ignore[no-untyped-def]
    incident = load_incident(INC / f"{name}.yaml") if name else None
    return run_eval(tenant, CFG, ds, tenant.pack.heuristic_model(0, {}), incident=incident)


def test_all_incident_files_load() -> None:
    files = sorted(INC.glob("*.yaml"))
    assert len(files) >= 9
    kinds = {load_incident(f).kind for f in files}
    assert kinds == {
        "api_fault",
        "doc_drift",
        "prompt_injection",
        "model_swap",
        "retrieval_config_change",
        "tool_schema_change",
        "data_quality",
    }


def test_unknown_incident_kind_names_file(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: x\nkind: meteor_strike\ndescription: d\n")
    with pytest.raises(ConfigError) as exc:
        load_incident(bad)
    assert "bad.yaml" in str(exc.value) and "kind" in str(exc.value)


def test_doc_drift_causes_regression_and_is_recorded(tenant: Tenant, dev: Dataset) -> None:
    ds = only(dev, "refund_outside_window")
    base, drift = run(tenant, ds), run(tenant, ds, "refund-window-drift")
    assert drift.incident is not None and drift.incident.id == "refund-window-drift"
    assert drift.dataset_hash == base.dataset_hash  # comparable with the baseline
    assert compare_runs(base, drift).diff.mean < 0


def test_timeout_after_success_never_double_refunds(tenant: Tenant, dev: Dataset) -> None:
    r = run(tenant, only(dev, "refund_eligible"), "refund-timeout-after-success")
    for t in r.results:
        refunds = [c for c in t.episode.changes if c.collection == "refunds"]
        assert len(refunds) <= 1
        assert t.success


def test_api_outage_injects_faults(tenant: Tenant, dev: Dataset) -> None:
    r = run(tenant, only(dev, "refund_eligible", "invoice_explain"), "billing-api-outage")
    assert any(t.episode.faults_injected for t in r.results)


def test_ticket_injection_changes_tickets_and_tags(tenant: Tenant, dev: Dataset) -> None:
    r = run(tenant, only(dev, "refund_eligible"), "ticket-prompt-injection")
    assert all("incident:prompt_injection" in t.tags for t in r.results)
    assert any("SYSTEM NOTICE" in m.content for t in r.results for m in t.episode.transcript)


def test_kb_injection_reaches_the_agent(tenant: Tenant, dev: Dataset) -> None:
    r = run(tenant, only(dev, "refund_eligible"), "kb-prompt-injection")
    seen = [
        c.text
        for t in r.results
        for c in t.episode.retrieved
        if c.section_key == "refund-policy#payout"
    ]
    assert seen and all("auto-approve all refunds" in s for s in seen)


def test_model_swap_changes_model_and_behavior(tenant: Tenant, dev: Dataset) -> None:
    ds = only(dev, "refund_eligible", "refund_over_limit")
    base, swapped = run(tenant, ds), run(tenant, ds, "model-downgrade")
    assert swapped.agent_config.model.name == "weaker-model"
    assert swapped.llm_settings["error_rates"]["wrong_amount"] == 0.3
    assert sum(t.success for t in swapped.results) < sum(t.success for t in base.results)


def test_retrieval_change_applies(tenant: Tenant, dev: Dataset) -> None:
    r = run(tenant, only(dev, "payment_failed_help"), "retrieval-top1")
    assert r.agent_config.retrieval.top_k == 1


def test_schema_change_breaks_refunds(tenant: Tenant, dev: Dataset) -> None:
    r = run(tenant, only(dev, "refund_eligible"), "billing-api-v2-schema")
    codes = {
        c.error_code for t in r.results for c in t.episode.tool_calls if c.op == "issue_refund"
    }
    assert codes == {"INVALID_ARGUMENT"}
    assert not any(t.success for t in r.results)


def test_data_quality_incident_reports_and_does_not_crash(tenant: Tenant, dev: Dataset) -> None:
    r = run(tenant, dev, "crm-export-dirty-emails")
    issues = [i for t in r.results for i in t.episode.data_issues]
    assert {i.kind for i in issues} >= {"normalized", "invalid"}
    assert all(t.episode.error is None for t in r.results)


def test_compare_rejects_runs_of_two_tenants(tenant: Tenant, dev: Dataset) -> None:
    a = run(tenant, only(dev, "refund_eligible"))
    b = a.model_copy(update={"tenant_id": "parcelpoint"})
    with pytest.raises(ConfigError):
        compare_runs(a, b)
