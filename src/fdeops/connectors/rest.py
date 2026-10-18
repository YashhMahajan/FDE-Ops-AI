"""A REST connector that a YAML file configures: no code for each customer API.

An FDE maps each tool operation to an HTTP endpoint, maps the argument names to the field names of
the customer API, and maps the response fields back. HTTP errors become typed tool errors. The
secret comes from an environment variable and never shows in an error message.
"""

import os
import time
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

import httpx

from fdeops.connectors.base import ErrorCode, OpContext, OpResult, OpSpec, ToolError
from fdeops.core.config import load_model
from fdeops.core.errors import ConfigError
from fdeops.core.model import FrozenModel

STATUS = {
    400: ErrorCode.INVALID_ARGUMENT,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.PERMISSION_DENIED,
    404: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    422: ErrorCode.INVALID_ARGUMENT,
    429: ErrorCode.RATE_LIMITED,
}


class RestAuth(FrozenModel):
    header: str = "Authorization"
    env: str
    prefix: str = ""


class RestResponseMap(FrozenModel):
    path: str | None = None
    """Dotted path to the useful part of the response, for example ``data.0``."""
    fields: dict[str, str] = {}
    """Our field name -> the field name in the customer API."""


class RestOperation(FrozenModel):
    name: str
    description: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str
    scope: str
    parameters: dict[str, Any]
    mutating: bool = False
    query: dict[str, str] = {}
    """API query parameter -> our argument name."""
    body: dict[str, str] = {}
    """API body field -> our argument name."""
    response: RestResponseMap = RestResponseMap()


class RestConnectorSpec(FrozenModel):
    name: str
    base_url: str
    auth: RestAuth | None = None
    timeout_s: float = 10.0
    operations: list[RestOperation]


def _dig(value: Any, path: str | None) -> Any:
    for part in path.split(".") if path else []:
        if isinstance(value, list) and part.isdigit():
            value = value[int(part)] if int(part) < len(value) else None
        elif isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


class RestConnector:
    def __init__(
        self, spec: RestConnectorSpec, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.name = spec.name
        self.spec = spec
        self._ops = {o.name: o for o in spec.operations}
        headers: dict[str, str] = {}
        self._secret = ""
        if spec.auth is not None:
            secret = os.environ.get(spec.auth.env)
            if not secret:
                raise ConfigError(
                    f"connector {spec.name!r} needs the environment variable {spec.auth.env}"
                )
            self._secret = secret
            headers[spec.auth.header] = f"{spec.auth.prefix}{secret}"
        self._client = httpx.Client(
            base_url=spec.base_url, headers=headers, timeout=spec.timeout_s, transport=transport
        )

    def ops(self) -> list[OpSpec]:
        return [
            OpSpec(
                name=o.name,
                description=o.description,
                parameters=o.parameters,
                mutating=o.mutating,
                required_scope=o.scope,
            )
            for o in self._ops.values()
        ]

    def _fail(self, code: ErrorCode, message: str) -> OpResult:
        if self._secret:
            message = message.replace(self._secret, "[SECRET]")
        return OpResult.failure(ToolError.of(code, message))

    def call(self, op: str, args: dict[str, Any], ctx: OpContext) -> OpResult:
        o = self._ops.get(op)
        if o is None:
            return self._fail(ErrorCode.INVALID_ARGUMENT, f"unknown operation {op!r}")
        try:
            path = o.path.format(**{k: quote(str(v), safe="") for k, v in args.items()})
        except KeyError as e:
            return self._fail(ErrorCode.INVALID_ARGUMENT, f"missing path argument {e}")
        params = {api: args[ours] for api, ours in o.query.items() if ours in args}
        body = {api: args[ours] for api, ours in o.body.items() if ours in args}
        headers = (
            {"Idempotency-Key": ctx.idempotency_key} if o.mutating and ctx.idempotency_key else {}
        )
        start = time.perf_counter()
        try:
            r = self._client.request(
                o.method,
                path,
                params=params or None,
                json=body if o.method != "GET" else None,
                headers=headers,
            )
        except httpx.TimeoutException:
            return self._fail(ErrorCode.TIMEOUT, f"{self.name} did not respond in time")
        except httpx.TransportError as e:
            return self._fail(ErrorCode.UNAVAILABLE, f"{self.name} is not available: {e}")
        latency = (time.perf_counter() - start) * 1000
        if r.status_code >= 400:
            code = STATUS.get(
                r.status_code,
                ErrorCode.UNAVAILABLE if r.status_code >= 500 else ErrorCode.INVALID_ARGUMENT,
            )
            return self._fail(code, f"{self.name} returned HTTP {r.status_code}: {r.text[:200]}")
        try:
            data = r.json() if r.content else {}
        except ValueError:
            return self._fail(ErrorCode.MALFORMED_RESPONSE, f"{self.name} did not return JSON")
        data = _dig(data, o.response.path)
        if o.response.fields:
            if not isinstance(data, dict):
                return self._fail(ErrorCode.MALFORMED_RESPONSE, "the response has no record")
            missing = [api for api in o.response.fields.values() if api not in data]
            if missing:
                return self._fail(
                    ErrorCode.MALFORMED_RESPONSE, f"the response does not have the fields {missing}"
                )
            data = {ours: data[api] for ours, api in o.response.fields.items()}
        return OpResult(ok=True, data=data, latency_ms=latency)


def load_rest_connector(path: Path, transport: httpx.BaseTransport | None = None) -> RestConnector:
    spec = load_model(path, RestConnectorSpec)
    try:
        return RestConnector(spec, transport=transport)
    except ConfigError as e:
        raise ConfigError(e.message, path) from e
