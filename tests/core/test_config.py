from pathlib import Path

import pytest

from fdeops.core.config import load_model, load_yaml
from fdeops.core.errors import ConfigError
from fdeops.core.model import FrozenModel


class Inner(FrozenModel):
    limit: int


class Outer(FrozenModel):
    name: str
    inner: Inner


def test_load_model_ok(tmp_path: Path) -> None:
    p = tmp_path / "ok.yaml"
    p.write_text("name: a\ninner:\n  limit: 3\n")
    assert load_model(p, Outer).inner.limit == 3


def test_load_model_error_names_field_and_file(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("name: a\ninner:\n  limit: lots\n")
    with pytest.raises(ConfigError) as exc:
        load_model(p, Outer)
    msg = str(exc.value)
    assert "bad.yaml" in msg
    assert "inner.limit" in msg


def test_load_yaml_rejects_non_mapping(tmp_path: Path) -> None:
    p = tmp_path / "list.yaml"
    p.write_text("- 1\n- 2\n")
    with pytest.raises(ConfigError):
        load_yaml(p)


def test_load_yaml_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as exc:
        load_yaml(tmp_path / "nope.yaml")
    assert "nope.yaml" in str(exc.value)


def test_frozen_model_forbids_extra() -> None:
    with pytest.raises(ValueError):
        Inner(limit=1, other=2)  # type: ignore[call-arg]
