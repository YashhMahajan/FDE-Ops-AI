import os
import threading
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


def test_enqueue_claim_complete(db: Database) -> None:
    q = JobQueue(db)
    job_id = q.enqueue("ledgerloop", "echo", {"x": 1})
    job = q.claim("w1")
    assert job is not None and job.id == job_id and job.status == "running"
    q.complete(job.id, {"ok": True})
    done = q.get(job_id)
    assert done.status == "succeeded" and done.result == {"ok": True}
    assert q.claim("w1") is None


def test_two_workers_never_claim_the_same_job(db: Database) -> None:
    q = JobQueue(db)
    ids = {q.enqueue("ledgerloop", "echo", {"i": i}) for i in range(30)}
    claimed: list[str] = []
    lock = threading.Lock()

    def work(name: str) -> None:
        while (job := q.claim(name)) is not None:
            with lock:
                claimed.append(job.id)
            q.complete(job.id, {})

    threads = [threading.Thread(target=work, args=(f"w{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(claimed) == sorted(ids)
    assert len(claimed) == len(set(claimed))


def test_expired_lease_is_reclaimed(db: Database) -> None:
    q = JobQueue(db, lease=timedelta(seconds=0))
    job_id = q.enqueue("ledgerloop", "echo", {})
    first = q.claim("w1")
    assert first is not None
    second = q.claim("w2")  # w1 stopped; its lease is already over
    assert second is not None and second.id == job_id and second.attempts == 2


def test_job_fails_after_max_attempts(db: Database) -> None:
    q = JobQueue(db, max_attempts=2)

    def boom(payload: dict) -> dict:  # type: ignore[type-arg]
        raise RuntimeError("upstream down")

    job_id = q.enqueue("ledgerloop", "boom", {})
    worker = Worker(q, {"boom": boom}, name="w1")
    assert worker.run_once() and worker.run_once()
    job = q.get(job_id)
    assert job.status == "failed" and "upstream down" in (job.error or "") and job.attempts == 2
    assert not worker.run_once()


def test_unknown_kind_fails_without_retry(db: Database) -> None:
    q = JobQueue(db)
    job_id = q.enqueue("ledgerloop", "nope", {})
    Worker(q, {}, name="w").run_once()
    assert q.get(job_id).status == "failed"


def test_worker_stops_after_the_current_job(db: Database) -> None:
    q = JobQueue(db)
    ids = [q.enqueue("ledgerloop", "slow", {}) for _ in range(3)]
    stop = threading.Event()
    seen: list[int] = []

    def slow(_payload: dict) -> dict:  # type: ignore[type-arg]
        seen.append(1)
        stop.set()  # a SIGTERM arrives while the first job runs
        return {"ok": True}

    t = threading.Thread(target=Worker(q, {"slow": slow}, "w").run_forever, args=(0.01, stop))
    t.start()
    t.join(timeout=10)
    assert not t.is_alive()
    assert len(seen) == 1  # the first job completed, and no new job started
    assert [q.get(i).status for i in ids].count("succeeded") == 1
    assert [q.get(i).status for i in ids].count("queued") == 2
