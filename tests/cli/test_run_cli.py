from pathlib import Path

from typer.testing import CliRunner

from fdeops.cli.main import app

ROOT = Path(__file__).parents[2]


def test_cli_run_end_to_end(tmp_path: Path) -> None:
    runner = CliRunner()
    built = runner.invoke(
        app,
        [
            "dataset",
            "build",
            "--tenant",
            str(ROOT / "tenants/ledgerloop"),
            "--out",
            str(tmp_path / "ds"),
        ],
    )
    assert built.exit_code == 0, built.output
    ds = tmp_path / "ds" / "ledgerloop" / "support-core@v1"
    args = [
        "run",
        "--tenant",
        str(ROOT / "tenants/ledgerloop"),
        "--agent",
        str(ROOT / "configs/agents/ledgerloop-heuristic.yaml"),
        "--dataset",
        str(ds),
        "--split",
        "dev",
        "--out",
        str(tmp_path / "runs"),
    ]
    first = runner.invoke(
        app, [*args, "--llm-mode", "record", "--cassettes", str(tmp_path / "c.jsonl")]
    )
    assert first.exit_code == 0, first.output
    assert "pipeline-test" in first.output
    replay = runner.invoke(
        app, [*args, "--llm-mode", "replay", "--cassettes", str(tmp_path / "c.jsonl")]
    )
    assert replay.exit_code == 0, replay.output
    runs = sorted((tmp_path / "runs").iterdir())
    assert len(runs) == 2
    report = runner.invoke(app, ["report", str(runs[0])])
    assert report.exit_code == 0 and "Provenance" in report.output
    cmp = runner.invoke(app, ["compare", str(runs[0]), str(runs[1])])
    assert cmp.exit_code == 0, cmp.output
    assert "+0.0" in cmp.output or "0.000" in cmp.output


def test_cli_replay_without_cassette_fails_cleanly(tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(
        app,
        [
            "dataset",
            "build",
            "--tenant",
            str(ROOT / "tenants/ledgerloop"),
            "--out",
            str(tmp_path / "ds"),
        ],
    )
    result = runner.invoke(
        app,
        [
            "run",
            "--tenant",
            str(ROOT / "tenants/ledgerloop"),
            "--agent",
            str(ROOT / "configs/agents/ledgerloop-heuristic.yaml"),
            "--dataset",
            str(tmp_path / "ds/ledgerloop/support-core@v1"),
            "--llm-mode",
            "replay",
            "--cassettes",
            str(tmp_path / "missing.jsonl"),
            "--out",
            str(tmp_path / "r"),
        ],
    )
    assert result.exit_code != 0
    assert "cassette" in result.output.lower()
