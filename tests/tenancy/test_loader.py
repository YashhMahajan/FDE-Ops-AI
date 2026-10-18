import shutil
from pathlib import Path

import pytest

from fdeops.core.errors import ConfigError
from fdeops.packs.billing.state import BillingState
from fdeops.tenancy.loader import load_tenant

LEDGERLOOP = Path(__file__).parents[2] / "tenants" / "ledgerloop"


def test_load_ledgerloop() -> None:
    t = load_tenant(LEDGERLOOP)
    assert t.config.id == "ledgerloop"
    assert t.pack.id == "billing"
    assert t.policy.refund_window_days == 14
    assert isinstance(t.base_world, BillingState)
    assert len(t.base_world.customers) == 40
    assert "refund-policy#refund-window" in t.kb
    assert t.config.datasets[0].name == "support-core"
    assert t.scopes == t.pack.agent_scopes


def test_non_fictional_tenant_rejected(tmp_path: Path) -> None:
    root = tmp_path / "t"
    shutil.copytree(LEDGERLOOP, root)
    cfg = root / "tenant.yaml"
    cfg.write_text(cfg.read_text().replace("fictional: true", "fictional: false"))
    with pytest.raises(ConfigError) as exc:
        load_tenant(root)
    assert "fictional" in str(exc.value)


def test_unknown_pack_rejected(tmp_path: Path) -> None:
    root = tmp_path / "t"
    shutil.copytree(LEDGERLOOP, root)
    cfg = root / "tenant.yaml"
    cfg.write_text(cfg.read_text().replace("pack: billing", "pack: nope"))
    with pytest.raises(ConfigError) as exc:
        load_tenant(root)
    assert "nope" in str(exc.value)


def test_scope_not_offered_by_pack_rejected(tmp_path: Path) -> None:
    root = tmp_path / "t"
    shutil.copytree(LEDGERLOOP, root)
    cfg = root / "tenant.yaml"
    cfg.write_text(cfg.read_text().replace("  - kb:read", "  - kb:read\n  - root:everything"))
    with pytest.raises(ConfigError):
        load_tenant(root)
