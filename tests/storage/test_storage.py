from pathlib import Path

import pytest

from fdeops.agent.config import load_agent_config
from fdeops.core.errors import ConfigError
from fdeops.eval.runner import run_eval
from fdeops.storage.artifacts import LocalArtifactStore
from fdeops.storage.db import Database
from fdeops.storage.keys import KeyStore, Role
from fdeops.storage.repo import NotFound, Repository
from fdeops.tenancy.loader import load_tenant

ROOT = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def small_run():  # type: ignore[no-untyped-def]
    t = load_tenant(ROOT / "tenants/ledgerloop")
    ds = t.build_datasets("support-core")["dev"]
    ds = ds.model_copy(update={"cases": ds.cases[:4]})
    cfg = load_agent_config(ROOT / "configs/agents/ledgerloop-heuristic.yaml")
    return run_eval(t, cfg, ds, t.pack.heuristic_model(0, {}))


def test_artifact_store_roundtrip_and_safety(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    uri = store.put_text("runs/ledgerloop/r1/run.json", "{}")
    assert store.get_text(uri) == "{}" and store.exists(uri)
    assert store.list("runs/ledgerloop") == ["runs/ledgerloop/r1/run.json"]
    with pytest.raises(ConfigError):
        store.put_text("../escape.txt", "x")


def test_repository_stores_runs_and_trials(db: Database, tmp_path: Path, small_run) -> None:  # type: ignore[no-untyped-def]
    store = LocalArtifactStore(tmp_path / "artifacts")
    with db.session() as s:
        repo = Repository(s, "ledgerloop", store)
        repo.save_run(small_run)
    with db.session() as s:
        repo = Repository(s, "ledgerloop", store)
        runs = repo.list_runs()
        assert [r.run_id for r in runs] == [small_run.run_id]
        assert runs[0].n_trials == 4 and 0 <= runs[0].success_rate <= 1
        assert repo.load_run(small_run.run_id) == small_run
        assert len(repo.trials(small_run.run_id)) == 4


def test_cross_tenant_read_is_not_found(db: Database, tmp_path: Path, small_run) -> None:  # type: ignore[no-untyped-def]
    store = LocalArtifactStore(tmp_path / "artifacts")
    with db.session() as s:
        Repository(s, "ledgerloop", store).save_run(small_run)
    with db.session() as s:
        other = Repository(s, "parcelpoint", store)
        assert other.list_runs() == []
        with pytest.raises(NotFound):
            other.load_run(small_run.run_id)


def test_repository_rejects_run_of_other_tenant(db: Database, tmp_path: Path, small_run) -> None:  # type: ignore[no-untyped-def]
    with db.session() as s, pytest.raises(ConfigError):
        Repository(s, "parcelpoint", LocalArtifactStore(tmp_path)).save_run(small_run)


def test_annotations_and_audit(db: Database, tmp_path: Path, small_run) -> None:  # type: ignore[no-untyped-def]
    store = LocalArtifactStore(tmp_path)
    with db.session() as s:
        repo = Repository(s, "ledgerloop", store)
        repo.save_run(small_run)
        r = small_run.results[0]
        repo.annotate(small_run.run_id, r.case_id, r.trial, "groundedness", True, "sam")
        repo.annotate(small_run.run_id, r.case_id, r.trial, "groundedness", False, "sam")
        labels = repo.human_labels(small_run.run_id, "groundedness")
        assert labels == {f"{r.case_id}:{r.trial}": False}  # the last label of one annotator wins
        repo.audit("sam", "annotate", r.case_id, "test")
        assert [e.action for e in repo.audit_events()] == ["annotate"]


def test_keys_are_hashed_and_roles_ordered(db: Database) -> None:
    with db.session() as s:
        keys = KeyStore(s)
        secret, record = keys.create("ledgerloop", "sam", Role.APPROVER)
        assert secret.startswith("fdo_") and secret not in record.key_hash
    with db.session() as s:
        keys = KeyStore(s)
        p = keys.authenticate(secret)
        assert p is not None and p.tenant_id == "ledgerloop" and p.role == Role.APPROVER
        assert p.role.allows(Role.ENGINEER) and not p.role.allows(Role.ADMIN)
        assert keys.authenticate("fdo_wrong") is None
        keys.revoke(record.key_id)
    with db.session() as s:
        assert KeyStore(s).authenticate(secret) is None


def test_purge_tenant_deletes_only_that_tenant(db: Database, tmp_path: Path, small_run) -> None:  # type: ignore[no-untyped-def]
    from fdeops.storage.keys import KeyStore, Role
    from fdeops.storage.repo import purge_tenant

    store = LocalArtifactStore(tmp_path / "art")
    with db.session() as s:
        Repository(s, "ledgerloop", store).save_run(small_run)
        Repository(s, "ledgerloop", store).audit("sam", "run.saved", small_run.run_id, "")
        KeyStore(s).create("ledgerloop", "eng", Role.ENGINEER)
        KeyStore(s).create("parcelpoint", "pp", Role.ENGINEER)
    with db.session() as s:
        counts = purge_tenant(s, "ledgerloop", tmp_path / "art")
    assert counts["runs"] == 1 and counts["trials"] == len(small_run.results)
    assert counts["api_keys"] == 1 and counts["audit_events"] >= 1 and counts["artifact_files"] >= 1
    assert not (tmp_path / "art" / "runs" / "ledgerloop").exists()
    with db.session() as s:
        assert Repository(s, "ledgerloop", store).list_runs() == []
        assert KeyStore(s).list("parcelpoint")  # the other tenant keeps its data
