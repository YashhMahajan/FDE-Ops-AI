"""Production hardening of the API: limits, input rules, errors, headers, readiness, metrics."""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fdeops.api.app import Settings, create_app
from fdeops.api.security import RateLimiter
from fdeops.core.errors import ConfigError
from fdeops.storage.db import Database
from fdeops.storage.keys import KeyStore, Role

ROOT = Path(__file__).parents[2]


def make(tmp_path: Path, **overrides: object) -> tuple[TestClient, dict[str, str]]:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        artifacts_dir=tmp_path / "artifacts",
        tenants_dir=ROOT / "tenants",
        registry_dir=tmp_path / "releases",
        configs_dir=ROOT / "configs",
    )
    settings = replace(settings, **overrides)  # type: ignore[arg-type]
    app = create_app(settings)
    keys: dict[str, str] = {}
    with Database(settings.database_url).session() as s:
        ks = KeyStore(s)
        keys["admin"], _ = ks.create(None, "root", Role.ADMIN)
        keys["engineer"], _ = ks.create("ledgerloop", "eng", Role.ENGINEER)
        keys["viewer"], _ = ks.create("ledgerloop", "view", Role.VIEWER)
    return TestClient(app, raise_server_exceptions=False), keys


@pytest.fixture
def api(tmp_path: Path) -> Iterator[tuple[TestClient, dict[str, str]]]:
    client, keys = make(tmp_path)
    with client:
        yield client, keys


def h(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


BODY = {"agent_config": "agents/ledgerloop-heuristic.yaml", "split": "dev", "limit": 2}


def test_token_bucket_refills_with_time() -> None:
    now = [0.0]
    rl = RateLimiter(per_minute=60, burst=2, clock=lambda: now[0])
    assert rl.allow("k")[0] and rl.allow("k")[0]
    allowed, wait = rl.allow("k")
    assert not allowed and 0 < wait <= 1.0
    assert rl.allow("other")[0]  # each key has its own bucket
    now[0] += 1.0
    assert rl.allow("k")[0]


def test_rate_limit_gives_429_with_retry_after(tmp_path: Path) -> None:
    client, keys = make(tmp_path, rate_per_minute=4.0)
    with client:
        codes = [
            client.get("/v1/tenants", headers=h(keys["viewer"])).status_code for _ in range(15)
        ]
        assert codes[0] == 200 and 429 in codes
        r = client.get("/v1/tenants", headers=h(keys["viewer"]))
        assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
        # A different key has its own limit.
        assert client.get("/v1/tenants", headers=h(keys["admin"])).status_code == 200


def test_requests_that_start_work_have_a_lower_limit(tmp_path: Path) -> None:
    client, keys = make(tmp_path, expensive_per_minute=2.0)
    with client:
        url = "/v1/tenants/ledgerloop/runs"
        codes = [
            client.post(url, json=BODY, headers=h(keys["engineer"])).status_code for _ in range(5)
        ]
        assert codes[0] == 202 and codes[-1] == 429
        # Reads are not "work": they use the general limit.
        assert client.get(url, headers=h(keys["engineer"])).status_code == 200


def test_wrong_keys_are_limited_for_each_client(tmp_path: Path) -> None:
    client, _ = make(tmp_path, auth_failures_per_minute=3.0)
    with client:
        codes = [client.get("/v1/tenants", headers=h("wrong-key")).status_code for _ in range(8)]
        assert codes[0] == 401 and codes[-1] == 429


def test_large_body_is_413(tmp_path: Path) -> None:
    client, keys = make(tmp_path, max_body_bytes=200)
    with client:
        body = {**BODY, "agent_config": "agents/" + "x" * 300 + ".yaml"}
        r = client.post("/v1/tenants/ledgerloop/runs", json=body, headers=h(keys["engineer"]))
        assert r.status_code == 413 and "request_id" in r.json()


@pytest.mark.parametrize("tenant", ["..", "LEDGERLOOP", "a" * 80, "ledger loop"])
def test_bad_tenant_ids_are_not_found(api, tenant: str) -> None:  # type: ignore[no-untyped-def]
    client, keys = api
    r = client.get(f"/v1/tenants/{tenant}/runs", headers=h(keys["admin"]))
    assert r.status_code == 404


@pytest.mark.parametrize(
    "change",
    [
        {"unknown_field": 1},
        {"limit": 10_001},
        {"trials": 11},
        {"dataset": "../x"},
        {"llm_settings": {"api_key": "x"}},
        {"llm_settings": {"error_rates": {"tool": 2.0}}},
    ],
)
def test_run_request_rejects_bad_input(api, change: dict) -> None:  # type: ignore[no-untyped-def, type-arg]
    client, keys = api
    r = client.post(
        "/v1/tenants/ledgerloop/runs", json={**BODY, **change}, headers=h(keys["engineer"])
    )
    assert r.status_code == 422, r.text


def test_query_bounds(api) -> None:  # type: ignore[no-untyped-def]
    client, keys = api
    hv = h(keys["viewer"])
    assert client.get("/v1/tenants/ledgerloop/runs?limit=501", headers=hv).status_code == 422
    assert client.get("/v1/tenants/ledgerloop/runs?limit=5&offset=0", headers=hv).status_code == 200
    r = client.get("/v1/tenants/ledgerloop/runs/x/impact?draws=1000000000", headers=hv)
    assert r.status_code == 422


def test_security_headers(api) -> None:  # type: ignore[no-untyped-def]
    client, keys = api
    r = client.get("/v1/tenants", headers=h(keys["viewer"]))
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["Cache-Control"] == "no-store"
    assert r.headers["x-request-id"].startswith("req_")


def test_unhandled_error_is_500_without_internals(tmp_path: Path) -> None:
    client, _ = make(tmp_path)

    @client.app.get("/v1/boom")  # type: ignore[attr-defined, untyped-decorator]
    def boom() -> None:
        raise RuntimeError("secret detail: postgres://user:pw@host")

    with client:
        r = client.get("/v1/boom")
    assert r.status_code == 500
    assert r.json()["detail"] == "internal error" and r.json()["request_id"].startswith("req_")
    assert "secret" not in r.text and "postgres" not in r.text


def test_ready_and_metrics(api) -> None:  # type: ignore[no-untyped-def]
    client, keys = api
    r = client.get("/ready")
    assert r.status_code == 200 and r.json()["checks"]["database"] is True
    client.get("/v1/tenants", headers=h(keys["viewer"]))
    assert client.get("/metrics", headers=h(keys["viewer"])).status_code == 403
    m = client.get("/metrics", headers=h(keys["admin"]))
    assert m.status_code == 200
    assert 'fdeops_http_requests_total{method="GET",route="/v1/tenants",status="200"}' in m.text
    assert "fdeops_http_request_seconds_bucket" in m.text


def test_ready_is_503_when_a_folder_is_missing(tmp_path: Path) -> None:
    client, _ = make(tmp_path)
    with client:
        (tmp_path / "artifacts").rename(tmp_path / "moved")
        r = client.get("/ready")
    assert r.status_code == 503 and r.json()["checks"]["artifacts"] is False


def test_settings_fail_fast(tmp_path: Path) -> None:
    base = Settings(
        database_url="sqlite://",
        artifacts_dir=tmp_path,
        tenants_dir=tmp_path / "missing",
        registry_dir=tmp_path,
        configs_dir=ROOT / "configs",
    )
    with pytest.raises(ConfigError):
        base.validate()
    ok = replace(base, tenants_dir=ROOT / "tenants", cors_origins=("*",))
    with pytest.raises(ConfigError):
        ok.validate()
