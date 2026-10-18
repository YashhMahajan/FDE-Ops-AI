from datetime import UTC, datetime
from typing import Any

import pytest

from fdeops.connectors.base import (
    ConnectorRegistry,
    ErrorCode,
    InProcessConnector,
    OpContext,
    OpFailure,
    OpSpec,
    ToolError,
)
from fdeops.core.clock import FakeClock

SCHEMA = {
    "type": "object",
    "properties": {"x": {"type": "integer"}},
    "required": ["x"],
    "additionalProperties": False,
}


def ctx() -> OpContext:
    return OpContext(
        tenant_id="t",
        actor="agent",
        scopes=frozenset({"s"}),
        clock=FakeClock(datetime(2026, 1, 1, tzinfo=UTC)),
    )


def spec(name: str) -> OpSpec:
    return OpSpec(name=name, description="d", parameters=SCHEMA, mutating=False, required_scope="s")


def double(args: dict[str, Any], _: OpContext) -> Any:
    return {"y": args["x"] * 2}


def boom(args: dict[str, Any], _: OpContext) -> Any:
    raise RuntimeError("kaboom")


def missing(args: dict[str, Any], _: OpContext) -> Any:
    raise OpFailure(ToolError(code=ErrorCode.NOT_FOUND, message="no", retryable=False))


def conn() -> InProcessConnector:
    return InProcessConnector(
        "c",
        {
            "double": (spec("double"), double),
            "boom": (spec("boom"), boom),
            "missing": (spec("missing"), missing),
        },
    )


def test_ok_call() -> None:
    r = conn().call("double", {"x": 2}, ctx())
    assert r.ok and r.data == {"y": 4}


def test_schema_violation_is_invalid_argument() -> None:
    r = conn().call("double", {"x": "two"}, ctx())
    assert not r.ok
    assert r.error is not None and r.error.code == ErrorCode.INVALID_ARGUMENT
    r2 = conn().call("double", {}, ctx())
    assert r2.error is not None and r2.error.code == ErrorCode.INVALID_ARGUMENT


def test_handler_exception_is_internal_not_raised() -> None:
    r = conn().call("boom", {"x": 1}, ctx())
    assert r.error is not None and r.error.code == ErrorCode.INTERNAL


def test_op_failure_maps_to_error() -> None:
    r = conn().call("missing", {"x": 1}, ctx())
    assert r.error == ToolError(code=ErrorCode.NOT_FOUND, message="no", retryable=False)


def test_unknown_op() -> None:
    reg = ConnectorRegistry([conn()])
    r = reg.call("nope", {}, ctx())
    assert r.error is not None and r.error.code == ErrorCode.INVALID_ARGUMENT
    assert "unknown operation" in r.error.message


def test_registry_routes_and_lists_specs() -> None:
    reg = ConnectorRegistry([conn()])
    assert {s.name for s in reg.specs()} == {"double", "boom", "missing"}
    assert reg.call("double", {"x": 5}, ctx()).data == {"y": 10}


def test_registry_rejects_duplicate_op_names() -> None:
    with pytest.raises(ValueError):
        ConnectorRegistry([conn(), conn()])
