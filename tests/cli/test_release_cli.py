import json
import re
from pathlib import Path

from typer.testing import CliRunner

from fdeops.cli.main import app

ROOT = Path(__file__).parents[2]
TENANT = str(ROOT / "tenants/ledgerloop")


def test_release_lifecycle_end_to_end(tmp_path: Path) -> None:
    r = CliRunner()
    ds = tmp_path / "ds" / "ledgerloop" / "support-core@v1"
    assert (
        r.invoke(
            app, ["dataset", "build", "--tenant", TENANT, "--out", str(tmp_path / "ds")]
        ).exit_code
        == 0
    )
    stale = str(ROOT / "configs/agents/ledgerloop-heuristic-stale.yaml")
    runs = tmp_path / "runs"
    for split in ("test", "dev"):
        res = r.invoke(
            app,
            [
                "run",
                "--tenant",
                TENANT,
                "--agent",
                stale,
                "--dataset",
                str(ds),
                "--split",
                split,
                "--out",
                str(runs),
            ],
        )
        assert res.exit_code == 0, res.output
    by_split = {
        json.loads((p / "run.json").read_text())["dataset_split"]: p for p in runs.iterdir()
    }
    reg = ["--registry", str(tmp_path / "releases")]

    # v1: the current (stale) configuration goes to production first.
    res = r.invoke(
        app,
        [
            "release",
            "propose",
            "--tenant",
            TENANT,
            "--candidate",
            str(by_split["test"]),
            "--dataset",
            str(ds),
            "--version",
            "v1",
            "--accept-failed-gates",
            "first release before the incident",
            *reg,
        ],
    )
    assert res.exit_code == 0, res.output
    d1 = re.search(r"(dec_\w+)", res.output).group(1)  # type: ignore[union-attr]
    bad = r.invoke(
        app,
        [
            "release",
            "approve",
            d1,
            "--tenant",
            TENANT,
            "--approver",
            "eve",
            "--role",
            "engineer",
            *reg,
        ],
    )
    assert bad.exit_code == 1 and "cannot approve" in bad.output
    ok = r.invoke(
        app,
        [
            "release",
            "approve",
            d1,
            "--tenant",
            TENANT,
            "--approver",
            "sam",
            "--role",
            "approver",
            *reg,
        ],
    )
    assert ok.exit_code == 0, ok.output

    # The improvement loop proposes v2. It waits for approval.
    res = r.invoke(
        app,
        [
            "improve",
            "--tenant",
            TENANT,
            "--dev-run",
            str(by_split["dev"]),
            "--dataset",
            str(ds),
            "--version",
            "v2",
            "--out",
            str(runs),
            *reg,
        ],
    )
    assert res.exit_code == 0, res.output
    assert "pending_approval" in res.output
    d2 = re.search(r"decision (dec_\w+)", res.output).group(1)  # type: ignore[union-attr]
    status = r.invoke(app, ["release", "status", "--tenant", TENANT, *reg])
    assert "production: v1" in status.output and d2 in status.output
    assert (
        r.invoke(
            app,
            [
                "release",
                "approve",
                d2,
                "--tenant",
                TENANT,
                "--approver",
                "sam",
                "--role",
                "approver",
                *reg,
            ],
        ).exit_code
        == 0
    )
    assert "production: v2" in r.invoke(app, ["release", "status", "--tenant", TENANT, *reg]).output
    memo = r.invoke(app, ["release", "memo", d2, "--tenant", TENANT, *reg])
    assert "## Gates" in memo.output
    back = r.invoke(
        app,
        [
            "release",
            "rollback",
            "--tenant",
            TENANT,
            "--approver",
            "sam",
            "--role",
            "approver",
            "--reason",
            "drill",
            *reg,
        ],
    )
    assert back.exit_code == 0 and "v1" in back.output
