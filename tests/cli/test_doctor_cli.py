from pathlib import Path

from typer.testing import CliRunner

from fdeops.cli.doctor import FAIL, OK, WARN, run_checks
from fdeops.cli.main import app

ROOT = Path(__file__).parents[2]


def _by_name(rows: list[tuple[str, str, str]]) -> dict[str, str]:
    return {check: status for status, check, _ in rows}


def test_doctor_passes_with_a_valid_tenant(tmp_path: Path) -> None:
    rows = run_checks(ROOT / "tenants" / "ledgerloop", {"FDEOPS_ARTIFACTS_DIR": str(tmp_path)})
    status = _by_name(rows)
    assert status["tenant"] == OK and status["python"] == OK
    assert status["model key"] == WARN
    assert FAIL not in status.values()


def test_doctor_reports_a_model_key_only_when_it_is_set(tmp_path: Path) -> None:
    env = {"FDEOPS_ARTIFACTS_DIR": str(tmp_path), "OPENROUTER_API_KEY": "k"}
    assert _by_name(run_checks(None, env))["model key"] == OK


def test_doctor_fails_for_a_broken_tenant(tmp_path: Path) -> None:
    (tmp_path / "tenant.yaml").write_text("id: x\n")
    result = CliRunner().invoke(app, ["doctor", "--tenant", str(tmp_path)])
    assert result.exit_code == 1
    assert "[fail] tenant" in result.output and "1 failure(s)" in result.output


def test_doctor_never_prints_the_key() -> None:
    result = CliRunner().invoke(app, ["doctor"], env={"OPENROUTER_API_KEY": "sk-secret-value"})
    assert "sk-secret-value" not in result.output
