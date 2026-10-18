from pathlib import Path

import pytest
from typer.testing import CliRunner

from fdeops.cli.main import app


def test_keys_create_list_revoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FDEOPS_DATABASE_URL", f"sqlite:///{tmp_path / 'k.db'}")
    r = CliRunner()
    created = r.invoke(
        app, ["keys", "create", "--name", "sam", "--role", "approver", "--tenant", "ledgerloop"]
    )
    assert created.exit_code == 0, created.output
    key_id = created.output.split()[0]
    secret = next(
        line.split()[1] for line in created.output.splitlines() if line.startswith("key:")
    )
    listed = r.invoke(app, ["keys", "list"])
    assert key_id in listed.output and secret not in listed.output and "active" in listed.output
    assert r.invoke(app, ["keys", "revoke", key_id]).exit_code == 0
    assert "revoked" in r.invoke(app, ["keys", "list"]).output


def test_tenant_key_needed_unless_admin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FDEOPS_DATABASE_URL", f"sqlite:///{tmp_path / 'k.db'}")
    res = CliRunner().invoke(app, ["keys", "create", "--name", "x", "--role", "viewer"])
    assert res.exit_code != 0
