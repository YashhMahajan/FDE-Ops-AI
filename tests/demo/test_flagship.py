import json
from pathlib import Path

from fdeops.agent.config import load_agent_config
from fdeops.demo.export import export_demo
from fdeops.demo.flagship import load_flagship_incident, run_flagship
from fdeops.devtools.ste import check_text, load_rules
from fdeops.tenancy.loader import load_tenant

ROOT = Path(__file__).parents[2]


def test_flagship_demo_end_to_end(tmp_path: Path) -> None:
    tenant = load_tenant(ROOT / "tenants/ledgerloop")
    config = load_agent_config(ROOT / "configs/agents/ledgerloop-heuristic.yaml")
    res = run_flagship(
        tenant,
        config,
        tenant.pack.heuristic_model(0, {}),
        load_flagship_incident(ROOT, tenant),
        tmp_path / "demo",
    )
    keys = [s.key for s in res.steps]
    assert keys == ["release_v1", "incident", "regression", "diagnosis", "release_v2", "impact"]
    # The label-free monitor sees the incident, and its alerts stop after the fix.
    assert {"stale_context", "critical_flag"} <= {
        a.signal for a in res.monitors["during_incident"].alerts
    }
    assert res.monitors["after_fix"].alerts == []
    # The incident causes a regression, and the fix removes it.
    assert res.comparisons["v1_vs_monitor"].diff.mean < 0
    assert res.comparisons["monitor_vs_v2"].diff.mean > 0
    assert res.diagnosis is not None
    assert res.diagnosis.clusters[0].cluster.failure_class == "stale_knowledge"
    assert res.diagnosis.clusters[0].verdict.value == "confirmed by intervention"
    assert res.improvement is not None and res.improvement.status == "pending_approval"
    assert res.registry is not None and res.registry.production().version == "v2"  # type: ignore[union-attr]
    assert res.roi is not None and res.roi.monthly_savings_vs_baseline is not None
    assert res.opportunities and res.opportunities[0].decision == "build"
    rules = load_rules()
    for name, text in res.reports.items():
        assert check_text(text, rules, name) == [], name
    out = export_demo(res, tmp_path / "web" / "ledgerloop")
    index = json.loads((out / "index.json").read_text())
    # The FAQ baseline uses no model, thus its numbers are measured. The agent runs are not.
    assert index["provenance"] == ["measured-in-simulation", "pipeline-test"]
    assert len(index["steps"]) == 6 and index["detail_runs"]
    run_id = index["detail_runs"][0]
    assert any((out / "trials" / run_id).iterdir())
    assert (out / "releases.json").exists() and (out / "impact.json").exists()
    assert (out / "monitor.json").exists()
    manifest = json.loads((tmp_path / "web" / "manifest.json").read_text())
    assert manifest["tenants"] == [
        {"id": "ledgerloop", "display_name": "Ledgerloop (fictional)", "pack": "billing"}
    ]
