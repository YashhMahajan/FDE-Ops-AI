"""A job that runs longer than its lease must run once, and a stale worker must not win."""

import os
import threading
import time
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest

from fdeops.jobs.queue import JobQueue
from fdeops.jobs.worker import Worker
from fdeops.storage.db import Database


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    url = os.environ.get("FDEOPS_TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'q.db'}"
    d = Database(url)
    d.reset()
    yield d
    d.dispose()


def test_a_long_job_runs_once_when_a_second_worker_polls(db: Database) -> None:
    q = JobQueue(db, lease=timedelta(seconds=0.6))
    q.enqueue("ledgerloop", "slow", {})
    runs: list[str] = []

    def slow(_payload: dict) -> dict:  # type: ignore[type-arg]
        runs.append("run")
        time.sleep(2.0)  # more than three times the lease
        return {"ok": True}

    first = Worker(q, {"slow": slow}, name="w1")
    second = Worker(q, {"slow": slow}, name="w2")
    t = threading.Thread(target=first.run_once)
    t.start()
    deadline = time.monotonic() + 1.8
    while time.monotonic() < deadline:  # the second worker polls while the first works
        second.run_once()
        time.sleep(0.1)
    t.join()
    assert runs == ["run"]
    job = q.get(next(iter(_job_ids(db))))
    assert job.status == "succeeded" and job.attempts == 1


def _job_ids(db: Database) -> list[str]:
    from sqlalchemy import select

    from fdeops.storage.db import JobRow

    with db.session() as s:
        return list(s.scalars(select(JobRow.id)))


def test_a_stale_worker_cannot_overwrite_the_result(db: Database) -> None:
    q = JobQueue(db, lease=timedelta(seconds=0.05))
    job_id = q.enqueue("ledgerloop", "echo", {})
    stale = q.claim("w1")
    assert stale is not None
    time.sleep(0.1)  # the lease of w1 expires
    current = q.claim("w2")
    assert current is not None and current.id == job_id and current.attempts == 2
    assert q.complete(job_id, {"from": "w2"}, worker="w2") is True
    assert q.complete(job_id, {"from": "w1"}, worker="w1") is False  # w1 lost the lease
    assert q.fail(job_id, "late failure of w1", worker="w1") is False
    done = q.get(job_id)
    assert done.status == "succeeded" and done.result == {"from": "w2"} and done.error is None


def test_a_long_error_message_is_cut(db: Database) -> None:
    q = JobQueue(db)
    job_id = q.enqueue("ledgerloop", "echo", {})
    q.claim("w1")
    q.fail(job_id, "x" * 50_000, retry=False)
    error = q.get(job_id).error
    assert error is not None and len(error) <= 2_100


def test_the_worker_survives_a_database_error(db: Database) -> None:
    q = JobQueue(db)
    q.enqueue("ledgerloop", "echo", {})
    calls = {"n": 0}
    real_claim = q.claim

    def flaky(worker: str):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("connection reset by peer")
        return real_claim(worker)

    q.claim = flaky  # type: ignore[method-assign]
    stop = threading.Event()
    worker = Worker(q, {"echo": lambda p: {"ok": True}}, name="w1")
    t = threading.Thread(target=worker.run_forever, kwargs={"idle_s": 0.05, "stop": stop})
    t.start()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and q.get(_job_ids(db)[0]).status != "succeeded":
        time.sleep(0.05)
    stop.set()
    t.join(timeout=5)
    assert q.get(_job_ids(db)[0]).status == "succeeded"
