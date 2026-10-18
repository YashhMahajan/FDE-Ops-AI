# M7: Storage, API, Jobs and Authentication

*Language: ASD-STE100. Refer to the [glossary](../glossary.md). Design: section 5.15.*

**Goal.** Make the platform a service that a team can share. The service has a database, an artifact store, a job queue, and an API with keys and roles. Each request goes through a tenant guard.

## Global constraints

- All M0 to M6 constraints apply.
- Local tests use SQLite and the FastAPI test client. They do not start a server.
- The same code operates on Postgres. CI runs the Postgres tests in a service container.
- The job queue uses the database. On Postgres, a worker claims a job with `FOR UPDATE SKIP LOCKED`. There is no Redis and no Celery.
- An API key is stored only as a hash. The service shows the key one time, when it makes the key.
- Each request has a tenant scope. A key for one tenant cannot read or change data of a different tenant. Only the `admin` role can see all tenants.
- Each log line is JSON and has a request ID.

## Tasks

| Task | Scope | Files | Tests |
|---|---|---|---|
| 1 | Database tables and sessions (SQLite and Postgres) | `storage/db.py` | `tests/storage/test_db.py` |
| 2 | Artifact store (local folder) | `storage/artifacts.py` | `tests/storage/test_artifacts.py` |
| 3 | Repository with a tenant scope: runs, trials, annotations, audit | `storage/repo.py` | `tests/storage/test_repo.py` |
| 4 | API keys and roles | `storage/keys.py` | `tests/storage/test_keys.py` |
| 5 | Job queue with leases, retries and a worker | `jobs/` | `tests/jobs/test_queue.py` |
| 6 | FastAPI service: health, tenants, runs, reports, traces, jobs, comparisons, annotations, calibration, releases | `api/` | `tests/api/test_api.py` |
| 7 | CLI: `fdeops serve`, `fdeops worker`, `fdeops keys` | `cli/serve.py` | `tests/cli/test_keys_cli.py` |

## Review items

| Failure mode | Correct behavior | Test |
|---|---|---|
| A key of tenant A requests a run of tenant B | HTTP 404. The response does not show if the run is there. | `test_cross_tenant_read_is_not_found` |
| Two workers claim jobs at the same time | Each job goes to one worker only | `test_two_workers_never_claim_the_same_job` |
| A worker stops while it has a job | The lease expires and a different worker gets the job | `test_expired_lease_is_reclaimed` |
| A job fails each time | The job stops after the maximum number of tries with status `failed` and the error | `test_job_fails_after_max_attempts` |
| A viewer key tries to approve a release | HTTP 403 | `test_viewer_cannot_approve` |
