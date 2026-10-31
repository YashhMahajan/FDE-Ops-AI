import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from fdeops.connectors.base import ErrorCode, OpContext
from fdeops.connectors.rest import RestConnector, RestConnectorSpec, load_rest_connector
from fdeops.core.clock import FakeClock
from fdeops.core.errors import ConfigError

SPEC = {
    "name": "crm",
    "base_url": "https://crm.customer.example/api",
    "auth": {"header": "Authorization", "env": "CRM_TOKEN", "prefix": "Bearer "},
    "operations": [
        {
            "name": "lookup_customer",
            "description": "Find a contact.",
            "method": "GET",
            "path": "/contacts",
            "query": {"email": "email"},
            "scope": "accounts:read",
            "parameters": {
                "type": "object",
                "properties": {"email": {"type": "string"}},
                "required": ["email"],
                "additionalProperties": False,
            },
            "response": {
                "path": "data.0",
                "fields": {"id": "contactId", "email": "primaryEmail", "customer_id": "accountRef"},
            },
        },
        {
            "name": "issue_refund",
            "description": "Refund.",
            "method": "POST",
            "path": "/invoices/{invoice_id}/refunds",
            "scope": "billing:refund",
            "mutating": True,
            "body": {"amountMinor": "amount_cents", "note": "reason"},
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice_id": {"type": "string"},
                    "amount_cents": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["invoice_id", "amount_cents", "reason"],
                "additionalProperties": False,
            },
        },
    ],
}


def ctx(key: str | None = None) -> OpContext:
    return OpContext(
        tenant_id="t",
        actor="agent",
        scopes=frozenset({"accounts:read"}),
        clock=FakeClock(datetime(2026, 1, 1, tzinfo=UTC)),
        idempotency_key=key,
    )


def connector(handler: Any, monkeypatch: pytest.MonkeyPatch) -> RestConnector:
    monkeypatch.setenv("CRM_TOKEN", "secret-token")
    return RestConnector(
        RestConnectorSpec.model_validate(SPEC), transport=httpx.MockTransport(handler)
    )


def test_get_with_query_and_response_field_map(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def handler(r: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"] = str(r.url), r.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "contactId": "c1",
                        "primaryEmail": "a@b.example",
                        "accountRef": "acc_9",
                        "other": 1,
                    }
                ]
            },
        )

    r = connector(handler, monkeypatch).call("lookup_customer", {"email": "a@b.example"}, ctx())
    assert r.ok and r.data == {"id": "c1", "email": "a@b.example", "customer_id": "acc_9"}
    assert seen["url"] == "https://crm.customer.example/api/contacts?email=a%40b.example"
    assert seen["auth"] == "Bearer secret-token"


def test_post_path_body_map_and_idempotency_header(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def handler(r: httpx.Request) -> httpx.Response:
        seen["path"], seen["body"] = r.url.raw_path.decode(), json.loads(r.content)
        seen["key"] = r.headers.get("idempotency-key")
        return httpx.Response(201, json={"refundId": "r1"})

    r = connector(handler, monkeypatch).call(
        "issue_refund",
        {"invoice_id": "inv 1/x", "amount_cents": 500, "reason": "dup"},
        ctx(key="k-1"),
    )
    assert r.ok and r.data == {"refundId": "r1"}
    assert seen["path"] == "/api/invoices/inv%201%2Fx/refunds"
    assert seen["body"] == {"amountMinor": 500, "note": "dup"}
    assert seen["key"] == "k-1"


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, ErrorCode.INVALID_ARGUMENT),
        (401, ErrorCode.UNAUTHENTICATED),
        (403, ErrorCode.PERMISSION_DENIED),
        (404, ErrorCode.NOT_FOUND),
        (409, ErrorCode.CONFLICT),
        (422, ErrorCode.INVALID_ARGUMENT),
        (429, ErrorCode.RATE_LIMITED),
        (500, ErrorCode.UNAVAILABLE),
        (503, ErrorCode.UNAVAILABLE),
    ],
)
def test_http_status_maps_to_typed_error(
    status: int, code: ErrorCode, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = connector(lambda r: httpx.Response(status, text="no"), monkeypatch)
    r = c.call("lookup_customer", {"email": "x"}, ctx())
    assert r.error is not None and r.error.code == code


def test_non_json_response_is_malformed(monkeypatch: pytest.MonkeyPatch) -> None:
    c = connector(lambda r: httpx.Response(200, text="<html>"), monkeypatch)
    r = c.call("lookup_customer", {"email": "x"}, ctx())
    assert r.error is not None and r.error.code == ErrorCode.MALFORMED_RESPONSE


def test_missing_response_field_is_malformed(monkeypatch: pytest.MonkeyPatch) -> None:
    c = connector(lambda r: httpx.Response(200, json={"data": [{"contactId": "c1"}]}), monkeypatch)
    r = c.call("lookup_customer", {"email": "x"}, ctx())
    assert r.error is not None and r.error.code == ErrorCode.MALFORMED_RESPONSE
    assert "primaryEmail" in r.error.message


def test_transport_timeout_is_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(r: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=r)

    r = connector(handler, monkeypatch).call("lookup_customer", {"email": "x"}, ctx())
    assert r.error is not None and r.error.code == ErrorCode.TIMEOUT and r.error.retryable


def test_missing_secret_is_config_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CRM_TOKEN", raising=False)
    import yaml

    p = tmp_path / "crm.yaml"
    p.write_text(yaml.safe_dump(SPEC))
    with pytest.raises(ConfigError) as exc:
        load_rest_connector(p)
    assert "CRM_TOKEN" in str(exc.value)


def test_secret_never_in_error_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    c = connector(lambda r: httpx.Response(401, text="bad token secret-token"), monkeypatch)
    r = c.call("lookup_customer", {"email": "x"}, ctx())
    assert r.error is not None and "secret-token" not in r.error.message


def test_an_oversized_response_is_refused_without_reading_it_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read = {"bytes": 0}

    def chunks() -> Any:
        for _ in range(1_000):  # a service that never stops: 1 GB if a client reads it all
            read["bytes"] += 1_000_000
            yield b"x" * 1_000_000

    def handler(r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=chunks())

    spec = {**SPEC, "max_response_bytes": 100_000}
    monkeypatch.setenv("CRM_TOKEN", "secret-token")
    c = RestConnector(
        RestConnectorSpec.model_validate(spec), transport=httpx.MockTransport(handler)
    )
    r = c.call("lookup_customer", {"email": "a@b.example"}, ctx())
    assert not r.ok and r.error is not None and r.error.code.value == "MALFORMED_RESPONSE"
    assert "too large" in r.error.message
    assert read["bytes"] <= 2_000_000  # it stopped after the first chunks


def test_a_large_content_length_is_refused_before_the_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(r: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-length": "50000000"}, content=b"{}")

    r = connector(handler, monkeypatch).call("lookup_customer", {"email": "a@b.example"}, ctx())
    assert not r.ok and r.error is not None and "too large" in r.error.message
