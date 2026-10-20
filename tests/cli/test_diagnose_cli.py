from pathlib import Path

from typer.testing import CliRunner

from fdeops.cli.main import app

ROOT = Path(__file__).parents[2]
TENANT = str(ROOT / "tenants/ledgerloop")
STALE = str(ROOT / "configs/agents/ledgerloop-heuristic-stale.yaml")


def _run(tmp_path: Path, split: str) -> tuple[CliRunner, Path, Path]:
    runner = CliRunner()
    assert (
        runner.invoke(
            app, ["dataset", "build", "--tenant", TENANT, "--out", str(tmp_path / "ds")]
        ).exit_code
        == 0
    )
    ds = tmp_path / "ds" / "ledgerloop" / "support-core@v1"
    res = runner.invoke(
        app,
        [
            "run",
            "--tenant",
            TENANT,
            "--agent",
            STALE,
            "--dataset",
            str(ds),
            "--split",
            split,
            "--out",
            str(tmp_path / "runs"),
        ],
    )
    assert res.exit_code == 0, res.output
    return runner, ds, next((tmp_path / "runs").iterdir())


def test_cli_diagnose_writes_report(tmp_path: Path) -> None:
    runner, ds, run_dir = _run(tmp_path, "dev")
    res = runner.invoke(app, ["diagnose", str(run_dir), "--tenant", TENANT, "--dataset", str(ds)])
    assert res.exit_code == 0, res.output
    report = (run_dir / "diagnosis.md").read_text()
    assert "stale_knowledge:refund_outside_window" in report
    assert (run_dir / "diagnosis.json").exists()
    assert "confirmed by intervention" in res.output


def test_cli_diagnose_refuses_test_split(tmp_path: Path) -> None:
    runner, ds, run_dir = _run(tmp_path, "test")
    res = runner.invoke(app, ["diagnose", str(run_dir), "--tenant", TENANT, "--dataset", str(ds)])
    assert res.exit_code == 1
    assert "dev split" in res.output
