"""A worker runs jobs from the queue. Each job kind has a handler function."""

import logging
import threading
from collections.abc import Callable
from typing import Any

from fdeops.jobs.queue import JobQueue

log = logging.getLogger("fdeops.worker")
Handler = Callable[[dict[str, Any]], dict[str, Any]]


MAX_BACKOFF_S = 60.0


class _Heartbeat:
    """Extend the lease of a job in a thread while the handler works."""

    def __init__(self, queue: JobQueue, job_id: str, worker: str) -> None:
        self._queue, self._job_id, self._worker = queue, job_id, worker
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"lease-{job_id}", daemon=True)

    def _run(self) -> None:
        interval = max(0.05, self._queue.lease.total_seconds() / 3)
        while not self._stop.wait(interval):
            try:
                if not self._queue.heartbeat(self._job_id, self._worker):
                    log.warning("job %s: the lease is lost", self._job_id)
                    return
            except Exception:  # one missed beat is not fatal: the next one comes
                log.exception("job %s: the heartbeat failed", self._job_id)

    def __enter__(self) -> "_Heartbeat":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=5)


class Worker:
    def __init__(self, queue: JobQueue, handlers: dict[str, Handler], name: str) -> None:
        self.queue = queue
        self.handlers = handlers
        self.name = name

    def run_once(self) -> bool:
        """Run one job. Returns False when the queue has no job."""
        job = self.queue.claim(self.name)
        if job is None:
            return False
        handler = self.handlers.get(job.kind)
        if handler is None:
            self.queue.fail(
                job.id, f"no handler for job kind {job.kind!r}", retry=False, worker=self.name
            )
            return True
        with _Heartbeat(self.queue, job.id, self.name):
            try:
                result = handler({**job.payload, "_tenant_id": job.tenant_id, "_job_id": job.id})
            except Exception as e:  # noqa: BLE001 - a job failure must not stop the worker
                log.warning("job %s failed: %s", job.id, e)
                if not self.queue.fail(job.id, f"{type(e).__name__}: {e}", worker=self.name):
                    log.warning("job %s: the lease was lost, the failure is dropped", job.id)
                return True
        if not self.queue.complete(job.id, result, worker=self.name):
            log.warning("job %s: the lease was lost, the result is dropped", job.id)
        return True

    def run_forever(self, idle_s: float = 2.0, stop: threading.Event | None = None) -> None:
        """Run jobs until ``stop`` is set. The current job always completes before the stop.

        A deploy sends SIGTERM. The CLI sets ``stop``, thus the worker does not leave a job
        half done. If the process stops hard, the lease of the job expires, and a different
        worker runs it again.
        """
        stop = stop or threading.Event()
        failures = 0
        while not stop.is_set():
            try:
                busy = self.run_once()
                failures = 0
            except Exception:  # a database error must not kill the worker
                failures += 1
                delay = min(MAX_BACKOFF_S, idle_s * 2**failures)
                log.exception("worker %s: queue error, new try in %.0f s", self.name, delay)
                stop.wait(delay)
                continue
            if not busy:
                stop.wait(idle_s)
        log.info("worker %s stopped", self.name)
