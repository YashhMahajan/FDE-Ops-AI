from pathlib import Path

from fdeops.agent.config import load_agent_config
from fdeops.demo.flagship import load_flagship_incident, run_flagship
from fdeops.demo.portfolio import write_portfolio
from fdeops.devtools.ste import check_text, load_rules
from fdeops.tenancy.loader import load_tenant

ROOT = Path(__file__).parents[2]
TENANTS = ("ledgerloop", "parcelpoint")


def test_platform_code_names_no_tenant() -> None:
    """No code is for one tenant only. Packs hold domain code. CLI help texts may give examples."""
    offenders = [
        str(p.relative_to(ROOT))
        for p in (ROOT / "src" / "fdeops").rglob("*.py")
        if "packs" not in p.parts
        and "cli" not in p.parts
        and any(t in p.read_text(encoding="utf-8") for t in TENANTS)
    ]
    assert offenders == []


def test_generated_portfolio_documents(tmp_path: Path) -> None:
    results = []
    for tid in TENANTS:
        t = load_tenant(ROOT / "tenants" / tid)
        config = load_agent_config(ROOT / "configs" / "agents" / f"{tid}-heuristic.yaml")
        incident = load_flagship_incident(ROOT, t)
        results.append(
            run_flagship(t, config, t.pack.heuristic_model(0, {}), incident, tmp_path / tid)
        )
    written = write_portfolio(results, ROOT, tmp_path / "portfolio")
    names = {p.name for p in written}
    assert "benchmark-report.md" in names and "case-study-parcelpoint.md" in names
    assert "postmortem-ledgerloop-refund-window-drift.md" in names
    rules = load_rules()
    for p in written:
        text = p.read_text(encoding="utf-8")
        assert text.startswith("> **Provenance: pipeline-test**"), p.name
        findings = check_text(text, rules, p.name)
        assert findings == [], "\n".join(str(f) for f in findings[:10])
    study = (tmp_path / "portfolio" / "case-study-parcelpoint.md").read_text()
    assert "| Platform files that name a tenant | 0 |" in study
    post = (tmp_path / "portfolio" / "postmortem-ledgerloop-refund-window-drift.md").read_text()
    assert "First alarm: `stale_context`" in post and "confirmed by intervention" in post
