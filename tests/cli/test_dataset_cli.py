import json
from pathlib import Path

from typer.testing import CliRunner

from fdeops.cli.main import app

LEDGERLOOP = Path(__file__).parents[2] / "tenants" / "ledgerloop"


def test_cli_build_writes_manifest(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app, ["dataset", "build", "--tenant", str(LEDGERLOOP), "--out", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    manifest = json.loads(
        (tmp_path / "ledgerloop" / "support-core@v1" / "manifest.json").read_text()
    )
    total = manifest["splits"]["dev"]["n_cases"] + manifest["splits"]["test"]["n_cases"]
    assert total == 120
    assert "sha256:" in result.output


def test_cli_tenant_validate() -> None:
    result = CliRunner().invoke(app, ["tenant", "validate", str(LEDGERLOOP)])
    assert result.exit_code == 0, result.output
    assert "ledgerloop" in result.output
