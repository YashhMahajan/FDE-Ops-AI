# 0003: A Job Queue in Postgres, Not Celery and Redis

*Status: accepted.*

## Context

An evaluation, a diagnosis or an improvement loop can continue for minutes. The API must not wait for them. The platform uses Postgres for its records at this time.

## Decision

- A `jobs` table in the same database. A worker claims a job with `SELECT ... FOR UPDATE SKIP LOCKED`.
- Each claim has a lease. If a worker stops, the lease expires and a different worker gets the job.
- Each job has a maximum number of tries. After the last try, the status is `failed` with the error.
- On SQLite (local tests), the same code operates without `SKIP LOCKED`.

## Alternatives

- **Celery with Redis.** This adds two services and a second source of truth. The number of jobs is small.
- **A cloud queue.** This adds a dependency on one vendor.

## Results

- One less service to operate and to explain.
- A test makes sure that four workers at the same time do not claim the same job. CI runs it on Postgres.
- At a very high number of jobs, a dedicated queue is better. The interface of the queue is small, thus a change is possible.
