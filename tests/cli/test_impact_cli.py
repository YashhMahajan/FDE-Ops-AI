from pathlib import Path

from typer.testing import CliRunner

from fdeops.cli.main import app

ROOT = Path(__file__).parents[2]
TENANT = str(ROOT / "tenants/ledgerloop")


def test_baseline_impact_and_opportunities(tmp_path: Path) -> None:
    r = CliRunner()
    ds = tmp_path / "ds" / "ledgerloop" / "support-core@v1"
    r.invoke(app, ["dataset", "build", "--tenant", TENANT, "--out", str(tmp_path / "ds")])
    runs = tmp_path / "runs"
    res = r.invoke(
        app,
        [
            "run",
            "--tenant",
            TENANT,
            "--agent",
            str(ROOT / "configs/agents/ledgerloop-heuristic-stale.yaml"),
            "--dataset",
            str(ds),
            "--split",
            "dev",
            "--out",
            str(runs),
        ],
    )
    assert res.exit_code == 0, res.output
    agent_run = next(runs.iterdir())
    res = r.invoke(
        app,
        [
            "baseline",
            "--tenant",
            TENANT,
            "--dataset",
            str(ds),
            "--split",
            "dev",
            "--out",
            str(tmp_path / "base"),
        ],
    )
    assert res.exit_code == 0, res.output
    base_run = next((tmp_path / "base").iterdir())
    res = r.invoke(
        app,
        [
            "impact",
            str(agent_run),
            "--tenant",
            TENANT,
            "--baseline-run",
            str(base_run),
            "--draws",
            "2000",
        ],
    )
    assert res.exit_code == 0, res.output
    assert (agent_run / "impact.md").exists() and "FAQ baseline" in (
        agent_run / "impact.md"
    ).read_text()
    assert (
        r.invoke(
            app, ["diagnose", str(agent_run), "--tenant", TENANT, "--dataset", str(ds)]
        ).exit_code
        == 0
    )
    res = r.invoke(app, ["opportunities", str(agent_run), "--tenant", TENANT])
    assert res.exit_code == 0, res.output
    roadmap = (agent_run / "roadmap.md").read_text()
    assert "What we build next" in roadmap
    assert "`freshness_filter`" in roadmap


def test_opportunities_need_diagnosis(tmp_path: Path) -> None:
    r = CliRunner()
    ds = tmp_path / "ds" / "ledgerloop" / "support-core@v1"
    r.invoke(app, ["dataset", "build", "--tenant", TENANT, "--out", str(tmp_path / "ds")])
    r.invoke(
        app,
        [
            "run",
            "--tenant",
            TENANT,
            "--agent",
            str(ROOT / "configs/agents/ledgerloop-heuristic.yaml"),
            "--dataset",
            str(ds),
            "--split",
            "dev",
            "--out",
            str(tmp_path / "runs"),
        ],
    )
    run_dir = next((tmp_path / "runs").iterdir())
    res = r.invoke(app, ["opportunities", str(run_dir), "--tenant", TENANT])
    assert res.exit_code == 1 and "diagnose" in res.output
