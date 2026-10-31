from pathlib import Path

import pytest
from typer.testing import CliRunner

from fdeops.cli.init import slugify
from fdeops.cli.main import app
from fdeops.tenancy.loader import load_tenant

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize(
    ("pack", "pack_dir", "tenant_dir"),
    [("billing", "billing", "ledgerloop"), ("logistics", "logistics", "parcelpoint")],
)
def test_init_makes_a_tenant_that_loads_and_builds_datasets(
    tmp_path: Path, pack: str, pack_dir: str, tenant_dir: str
) -> None:
    target = tmp_path / "tenants" / "acme"
    result = CliRunner().invoke(app, ["init", str(target), "--pack", pack, "--name", "Acme Co"])
    assert result.exit_code == 0, result.output
    tenant = load_tenant(target)
    assert tenant.id == "acme-co" and tenant.company == "Acme Co"
    assert tenant.config.demo_incident is None
    datasets = tenant.build_datasets("support-core")
    assert datasets["dev"].cases and datasets["test"].cases
    # The starter files must stay equal to the files of the demo tenant of the same pack.
    demo = ROOT / "tenants" / tenant_dir
    for path in [demo / "policy.yaml", *sorted((demo / "kb").glob("*.md"))]:
        expected = path.read_text().replace(tenant_dir.capitalize(), "Acme Co")
        assert (target / path.relative_to(demo)).read_text() == expected
    assert "{{" not in "".join(p.read_text() for p in target.rglob("*") if p.is_file())


def test_init_writes_an_agent_config_when_a_configs_folder_exists(tmp_path: Path) -> None:
    (tmp_path / "configs" / "agents").mkdir(parents=True)
    result = CliRunner().invoke(
        app, ["init", str(tmp_path / "tenants" / "acme"), "--name", "Acme Co"]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "configs" / "agents" / "acme-co-heuristic.yaml").exists()


def test_init_refuses_a_folder_that_has_files(tmp_path: Path) -> None:
    (tmp_path / "keep.txt").write_text("x")
    result = CliRunner().invoke(app, ["init", str(tmp_path), "--name", "Acme Co"])
    assert result.exit_code == 1 and "not empty" in result.output
    assert (tmp_path / "keep.txt").read_text() == "x"


def test_init_refuses_a_bad_id_and_an_unknown_pack(tmp_path: Path) -> None:
    runner = CliRunner()
    bad_id = runner.invoke(app, ["init", str(tmp_path / "a"), "--name", "Acme", "--id", "A B"])
    assert bad_id.exit_code == 1 and "not valid" in bad_id.output
    bad_pack = runner.invoke(
        app, ["init", str(tmp_path / "b"), "--name", "Acme", "--pack", "healthcare"]
    )
    assert bad_pack.exit_code == 1 and "unknown pack" in bad_pack.output
    assert not (tmp_path / "a").exists() and not (tmp_path / "b").exists()


def test_slugify() -> None:
    assert slugify("  Acme & Sons, Inc.! ") == "acme-sons-inc"


def test_init_removes_the_folder_it_made_when_the_new_tenant_does_not_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fdeops.cli import init as init_module
    from fdeops.core.errors import ConfigError

    def broken(_root: Path) -> None:
        raise ConfigError("the starter policy is not valid")

    monkeypatch.setattr(init_module, "load_tenant", broken)
    target = tmp_path / "tenants" / "acme"
    result = CliRunner().invoke(app, ["init", str(target), "--name", "Acme Co"])
    assert result.exit_code == 1 and "not valid" in result.output
    assert not target.exists()
