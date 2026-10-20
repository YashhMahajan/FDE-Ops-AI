from pathlib import Path

import yaml
from typer.testing import CliRunner

from fdeops.cli.main import app

ROOT = Path(__file__).parents[2]


def _manifest(tmp: Path, cassette: Path, minimum: float) -> Path:
    m = tmp / "regression.yaml"
    m.write_text(
        yaml.safe_dump(
            {
                "checks": [
                    {
                        "name": "ledgerloop-heuristic-dev",
                        "tenant": str(ROOT / "tenants/ledgerloop"),
                        "agent": str(ROOT / "configs/agents/ledgerloop-heuristic.yaml"),
                        "dataset": "support-core",
                        "split": "dev",
                        "cassettes": str(cassette),
                        "min_success_lower": minimum,
                    }
                ]
            }
        )
    )
    return m


def test_record_then_regress_passes_and_fails_on_threshold(tmp_path: Path) -> None:
    r = CliRunner()
    cassette = tmp_path / "c.jsonl"
    rec = r.invoke(app, ["regress", str(_manifest(tmp_path, cassette, 0.5)), "--record"])
    assert rec.exit_code == 0, rec.output
    assert cassette.exists()
    ok = r.invoke(app, ["regress", str(_manifest(tmp_path, cassette, 0.5))])
    assert ok.exit_code == 0 and "pass" in ok.output
    bad = r.invoke(app, ["regress", str(_manifest(tmp_path, cassette, 0.999))])
    assert bad.exit_code == 1 and "fail" in bad.output


def test_regress_reports_missing_cassette(tmp_path: Path) -> None:
    res = CliRunner().invoke(app, ["regress", str(_manifest(tmp_path, tmp_path / "x.jsonl", 0.5))])
    assert res.exit_code == 1 and "cassette" in res.output.lower()


def test_regress_skip_missing(tmp_path: Path) -> None:
    m = _manifest(tmp_path, tmp_path / "x.jsonl", 0.5)
    res = CliRunner().invoke(app, ["regress", str(m), "--skip-missing"])
    assert res.exit_code == 0 and "skip" in res.output


def test_run_provider_override(tmp_path: Path) -> None:
    r = CliRunner()
    r.invoke(
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
    res = r.invoke(
        app,
        [
            "run",
            "--tenant",
            str(ROOT / "tenants/ledgerloop"),
            "--agent",
            str(ROOT / "configs/agents/ledgerloop-v1.yaml"),
            "--provider",
            "heuristic",
            "--dataset",
            str(tmp_path / "ds/ledgerloop/support-core@v1"),
            "--split",
            "dev",
            "--out",
            str(tmp_path / "runs"),
        ],
    )
    assert res.exit_code == 0, res.output
    assert "pipeline-test" in res.output


def test_regress_limit_and_model_override(tmp_path: Path) -> None:
    cassette = tmp_path / "small.jsonl"
    m = tmp_path / "regression.yaml"
    m.write_text(
        yaml.safe_dump(
            {
                "checks": [
                    {
                        "name": "small",
                        "tenant": str(ROOT / "tenants/ledgerloop"),
                        "agent": str(ROOT / "configs/agents/ledgerloop-v1.yaml"),
                        "provider": "heuristic",
                        "model": "rules",
                        "limit": 5,
                        "cassettes": str(cassette),
                        "min_success_lower": 0.0,
                    }
                ]
            }
        )
    )
    r = CliRunner()
    rec = r.invoke(app, ["regress", str(m), "--record"])
    assert rec.exit_code == 0, rec.output
    assert '"model": "rules"' in cassette.read_text() or "rules" in cassette.read_text()
    replay = r.invoke(app, ["regress", str(m)])
    assert replay.exit_code == 0 and "pass" in replay.output
