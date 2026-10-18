from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from fdeops.core.errors import ConfigError

M = TypeVar("M", bound=BaseModel)


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ConfigError("file not found", path) from e
    except yaml.YAMLError as e:
        raise ConfigError(f"invalid YAML: {e}", path) from e
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"expected a mapping at top level, got {type(raw).__name__}", path)
    return raw


def format_validation_error(err: ValidationError) -> str:
    parts = []
    for e in err.errors():
        loc = ".".join(str(p) for p in e["loc"])
        parts.append(f"{loc}: {e['msg']}")
    return "; ".join(parts)


def validate_model(data: Any, model: type[M], path: Path | None = None) -> M:
    try:
        return model.model_validate(data)
    except ValidationError as e:
        raise ConfigError(format_validation_error(e), path) from e


def load_model(path: Path, model: type[M]) -> M:
    return validate_model(load_yaml(path), model, path)
