from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fdeops.api.app import Settings, create_app
from fdeops.storage.db import Database
from fdeops.storage.keys import KeyStore, Role

ROOT = Path(__file__).parents[2]


@pytest.fixture
def env(tmp_path: Path) -> Iterator[tuple[TestClient, dict[str, str], Settings]]:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        artifacts_dir=tmp_path / "artifacts",
        tenants_dir=ROOT / "tenants",
        registry_dir=tmp_path / "releases",
        configs_dir=ROOT / "configs",
    )
    app = create_app(settings)
    db = Database(settings.database_url)
    keys: dict[str, str] = {}
    with db.session() as s:
        ks = KeyStore(s)
        keys["admin"], _ = ks.create(None, "root", Role.ADMIN)
        keys["engineer"], _ = ks.create("ledgerloop", "eng", Role.ENGINEER)
        keys["viewer"], _ = ks.create("ledgerloop", "view", Role.VIEWER)
        keys["approver"], _ = ks.create("ledgerloop", "sam", Role.APPROVER)
        keys["parcel"], _ = ks.create("parcelpoint", "pp", Role.ENGINEER)
    with TestClient(app) as client:
        yield client, keys, settings


def h(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def run_job(client: TestClient, keys: dict[str, str], body: dict) -> str:  # type: ignore[type-arg]
    r = client.post("/v1/tenants/ledgerloop/runs", json=body, headers=h(keys["engineer"]))
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    assert client.post("/v1/admin/worker/run-once", headers=h(keys["admin"])).status_code == 200
    job = client.get(f"/v1/tenants/ledgerloop/jobs/{job_id}", headers=h(keys["engineer"])).json()
    assert job["status"] == "succeeded", job
    return str(job["result"]["run_id"])


BODY = {
    "agent_config": "agents/ledgerloop-heuristic.yaml",
    "dataset": "support-core",
    "split": "dev",
    "limit": 6,
}


def test_health_needs_no_key(env) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = env
    assert client.get("/health").json()["status"] == "ok"


def test_requests_need_a_valid_key(env) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = env
    assert client.get("/v1/tenants").status_code == 401
    assert client.get("/v1/tenants", headers=h("fdo_nope")).status_code == 401


def test_tenant_listing_is_scoped(env) -> None:  # type: ignore[no-untyped-def]
    client, keys, _ = env
    all_ids = {t["id"] for t in client.get("/v1/tenants", headers=h(keys["admin"])).json()}
    assert {"ledgerloop", "parcelpoint"} <= all_ids
    mine = client.get("/v1/tenants", headers=h(keys["viewer"])).json()
    assert [t["id"] for t in mine] == ["ledgerloop"]


def test_run_lifecycle_report_trials_and_trace(env) -> None:  # type: ignore[no-untyped-def]
    client, keys, _ = env
    run_id = run_job(client, keys, BODY)
    base = f"/v1/tenants/ledgerloop/runs/{run_id}"
    v = h(keys["viewer"])
    summary = client.get(base, headers=v).json()
    assert summary["run_id"] == run_id and summary["provenance"] == "pipeline-test"
    assert client.get(f"{base}/report", headers=v).text.startswith("> **Provenance")
    trials = client.get(f"{base}/trials", headers=v).json()
    assert len(trials) == 6
    t0 = trials[0]
    detail = client.get(f"{base}/trials/{t0['case_id']}/{t0['trial']}", headers=v).json()
    assert detail["episode"]["trace"]["spans"]
    assert [r["run_id"] for r in client.get("/v1/tenants/ledgerloop/runs", headers=v).json()] == [
        run_id
    ]


def test_cross_tenant_read_is_not_found(env) -> None:  # type: ignore[no-untyped-def]
    client, keys, _ = env
    run_id = run_job(client, keys, BODY)
    r = client.get(f"/v1/tenants/ledgerloop/runs/{run_id}", headers=h(keys["parcel"]))
    assert r.status_code == 404
    r2 = client.get(f"/v1/tenants/parcelpoint/runs/{run_id}", headers=h(keys["parcel"]))
    assert r2.status_code == 404


def test_viewer_cannot_start_runs_or_approve(env) -> None:  # type: ignore[no-untyped-def]
    client, keys, _ = env
    r = client.post("/v1/tenants/ledgerloop/runs", json=BODY, headers=h(keys["viewer"]))
    assert r.status_code == 403
    r = client.post(
        "/v1/tenants/ledgerloop/releases/dec_x/approve",
        json={"comment": ""},
        headers=h(keys["viewer"]),
    )
    assert r.status_code == 403


def test_viewer_cannot_approve(env) -> None:  # type: ignore[no-untyped-def]
    test_viewer_cannot_start_runs_or_approve(env)


def test_bad_run_request_is_422_with_reason(env) -> None:  # type: ignore[no-untyped-def]
    client, keys, _ = env
    r = client.post(
        "/v1/tenants/ledgerloop/runs",
        json={**BODY, "agent_config": "../../etc"},
        headers=h(keys["engineer"]),
    )
    assert r.status_code == 422 and "agent_config" in r.text


def test_compare_and_diagnose(env) -> None:  # type: ignore[no-untyped-def]
    client, keys, _ = env
    a = run_job(client, keys, BODY)
    b = run_job(client, keys, {**BODY, "agent_config": "agents/ledgerloop-heuristic-stale.yaml"})
    cmp = client.get(f"/v1/tenants/ledgerloop/compare?a={a}&b={b}", headers=h(keys["viewer"]))
    assert cmp.status_code == 200 and "diff" in cmp.json()
    r = client.post(f"/v1/tenants/ledgerloop/runs/{b}/diagnose", headers=h(keys["engineer"]))
    assert r.status_code == 202
    client.post("/v1/admin/worker/run-once", headers=h(keys["admin"]))
    d = client.get(f"/v1/tenants/ledgerloop/runs/{b}/diagnosis", headers=h(keys["viewer"]))
    assert d.status_code == 200 and "clusters" in d.json()


def test_annotations_and_calibration(env) -> None:  # type: ignore[no-untyped-def]
    client, keys, _ = env
    run_id = run_job(client, keys, BODY)
    trials = client.get(
        f"/v1/tenants/ledgerloop/runs/{run_id}/trials", headers=h(keys["viewer"])
    ).json()
    for t in trials:
        r = client.post(
            "/v1/tenants/ledgerloop/annotations",
            headers=h(keys["engineer"]),
            json={
                "run_id": run_id,
                "case_id": t["case_id"],
                "trial": t["trial"],
                "rubric": "outcome",
                "label": t["success"],
            },
        )
        assert r.status_code == 201
    cal = client.get(
        f"/v1/tenants/ledgerloop/runs/{run_id}/calibration?rubric=outcome",
        headers=h(keys["viewer"]),
    ).json()
    assert cal["n"] == len(trials) and cal["agreement"] == 1.0


def test_audit_log_records_writes(env) -> None:  # type: ignore[no-untyped-def]
    client, keys, _ = env
    run_job(client, keys, BODY)
    events = client.get("/v1/tenants/ledgerloop/audit", headers=h(keys["approver"])).json()
    assert any(e["action"] == "run.requested" and e["actor"] == "eng" for e in events)


def test_request_id_header(env) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = env
    r = client.get("/health")
    assert r.headers.get("x-request-id", "").startswith("req_")
