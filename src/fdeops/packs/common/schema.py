from typing import Any

from fdeops.connectors.base import ErrorCode, OpFailure, OpSpec, Terminal

ID: dict[str, Any] = {"type": "string", "minLength": 1}
TEXT: dict[str, Any] = {"type": "string", "minLength": 1, "maxLength": 4000}


def obj(props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


def spec(
    name: str,
    desc: str,
    params: dict[str, Any],
    scope: str,
    mutating: bool = False,
    terminal: Terminal | None = None,
) -> OpSpec:
    return OpSpec(
        name=name,
        description=desc,
        parameters=params,
        required_scope=scope,
        mutating=mutating,
        terminal=terminal,
    )


def not_found(what: str) -> OpFailure:
    return OpFailure.of(ErrorCode.NOT_FOUND, f"{what} not found")
