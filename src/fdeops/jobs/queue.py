"""A job queue in the database. No Redis and no Celery: one less service to run (ADR-0004).

A worker claims a job with a lease. On Postgres, the claim uses ``FOR UPDATE SKIP LOCKED``, thus
two workers never get the same job. On SQLite, the database lock gives the same result. When a
worker stops, its lease expires and a different worker gets the job.
"""

from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select, update

from fdeops.core.errors import ConfigError, InvariantError
from fdeops.core.ids import new_id
from fdeops.core.model import FrozenModel
from fdeops.storage.db import Database, JobRow, utcnow


class Job(FrozenModel):
    id: str
    tenant_id: str
    kind: str
    payload: dict[str, Any]
    status: str
    attempts: int
    result: dict[str, Any] | None = None
    error: str | None = None


def _job(row: JobRow) -> Job:
    return Job(
        id=row.id,
        tenant_id=row.tenant_id,
        kind=row.kind,
        payload=row.payload,
        status=row.status,
        attempts=row.attempts,
        result=row.result,
        error=row.error,
    )


class JobQueue:
    def __init__(
        self, db: Database, lease: timedelta = timedelta(minutes=10), max_attempts: int = 3
    ) -> None:
        self.db = db
        self.lease = lease
        self.max_attempts = max_attempts

    def enqueue(self, tenant_id: str, kind: str, payload: dict[str, Any]) -> str:
        job_id = new_id("job")
        with self.db.session() as s:
            s.add(
                JobRow(
                    id=job_id,
                    tenant_id=tenant_id,
                    kind=kind,
                    payload=payload,
                    status="queued",
                    attempts=0,
                    created_at=utcnow(),
                )
            )
        return job_id

    def get(self, job_id: str, tenant_id: str | None = None) -> Job:
        with self.db.session() as s:
            row = s.get(JobRow, job_id)
            if row is None or (tenant_id is not None and row.tenant_id != tenant_id):
                raise ConfigError(f"job {job_id} not found")
            return _job(row)

    def claim(self, worker: str) -> Job | None:
        now = utcnow()
        claimable = or_(
            JobRow.status == "queued", (JobRow.status == "running") & (JobRow.locked_until <= now)
        )
        with self.db.session() as s:
            q = select(JobRow).where(claimable).order_by(JobRow.created_at, JobRow.id).limit(1)
            if not self.db.is_sqlite:
                q = q.with_for_update(skip_locked=True)
            row = s.scalars(q).first()
            if row is None:
                return None
            if row.attempts >= self.max_attempts:
                row.status, row.finished_at = "failed", now
                row.error = (row.error or "") + " (the lease expired after the last try)"
                return None
            # Compare-and-set: on SQLite another worker can have changed the row since the read.
            res = s.execute(
                update(JobRow)
                .where(JobRow.id == row.id, JobRow.attempts == row.attempts, claimable)
                .values(
                    status="running",
                    attempts=row.attempts + 1,
                    locked_by=worker,
                    locked_until=now + self.lease,
                )
            )
            if res.rowcount != 1:  # type: ignore[attr-defined]
                return None
            s.flush()
            s.refresh(row)
            return _job(row)

    def complete(self, job_id: str, result: dict[str, Any]) -> None:
        with self.db.session() as s:
            row = s.get(JobRow, job_id)
            if row is None:
                raise InvariantError("row must be set here")
            row.status, row.result, row.finished_at = "succeeded", result, utcnow()
            row.locked_by = row.locked_until = None

    def fail(self, job_id: str, error: str, retry: bool = True) -> None:
        with self.db.session() as s:
            row = s.get(JobRow, job_id)
            if row is None:
                raise InvariantError("row must be set here")
            row.error = error
            row.locked_by = row.locked_until = None
            if retry and row.attempts < self.max_attempts:
                row.status = "queued"
            else:
                row.status, row.finished_at = "failed", utcnow()
