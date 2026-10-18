"""A worker runs jobs from the queue. Each job kind has a handler function."""

import logging
import time
from collections.abc import Callable
from typing import Any

from fdeops.jobs.queue import JobQueue

log = logging.getLogger("fdeops.worker")
Handler = Callable[[dict[str, Any]], dict[str, Any]]


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
            self.queue.fail(job.id, f"no handler for job kind {job.kind!r}", retry=False)
            return True
        try:
            result = handler({**job.payload, "_tenant_id": job.tenant_id, "_job_id": job.id})
        except Exception as e:  # a job failure must not stop the worker
            log.warning("job %s failed: %s", job.id, e)
            self.queue.fail(job.id, f"{type(e).__name__}: {e}")
            return True
        self.queue.complete(job.id, result)
        return True

    def run_forever(self, idle_s: float = 2.0) -> None:  # pragma: no cover - a loop for deploys
        while True:
            if not self.run_once():
                time.sleep(idle_s)
