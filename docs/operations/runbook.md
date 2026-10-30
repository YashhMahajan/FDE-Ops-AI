# Operations Runbook

*Readers: the person on duty for the service.*

## 1. Parts of the service

| part | command | port | health |
|---|---|---|---|
| API | `fdeops serve --host 0.0.0.0` | 8000 | `GET /health` (the process answers), `GET /ready` (the database and the folders operate) |
| Worker | `fdeops worker` | none | The main process is the worker. The metric `fdeops_jobs` shows the queue. |
| Web UI | nginx in `docker/web.Dockerfile` | 8080 | `GET /` |
| Database | Postgres 16 | 5432 | `pg_isready` |

`GET /metrics` gives Prometheus metrics. It needs an admin key. Refer to the [configuration reference](configuration.md) for each setting.

## 2. Service levels

| measure | target | where to see it |
|---|---|---|
| Availability of the API | 99.5% of the minutes in 30 days, measured on `/ready` | the uptime monitor |
| Latency of read requests | p95 less than 500 ms | `fdeops_http_request_seconds` |
| Jobs that fail | less than 2% in 1 day | `fdeops_jobs{status="failed"}` |
| Queue | no job waits more than 15 minutes | `fdeops_jobs{status="queued"}` |

Send an alert to the person on duty when a target is not met for 15 minutes.

## 3. Deploy a new version

1. Read the release notes of the version. Find the database migrations of the version.
2. Make a backup of the database (section 5).
3. Run the migrations: `fdeops db upgrade`. The API and the worker also run them at start. A lock makes sure that only one process does it.
4. Deploy the new images: first the workers, then the API.
5. Examine `/ready` and the metrics for 15 minutes.

A migration must operate with the previous version of the code. Thus, a deploy needs no downtime. To remove a column, use two versions: first stop the use, then remove the column.

## 4. Roll back

- **The code.** Deploy the previous image. The migrations go forward only. If the previous code cannot use the new schema, restore the backup (section 5).
- **An agent release.** Use `fdeops release rollback`. A person with the approver role must do it. The release registry keeps a record.

## 5. Backups and restore

| item | how | interval | keep |
|---|---|---|---|
| Postgres | `pg_dump --format=custom` | each day | 30 days |
| Artifacts and the registry | a copy of the folders, or a snapshot of the volume | each day | 30 days |

Restore:

1. Stop the workers and the API.
2. Restore the database: `pg_restore --clean --dbname <url> <file>`.
3. Restore the artifact folder and the registry folder from the same day.
4. Start the API, then the workers. Examine `/ready`.

Do a test restore each month. A backup that nobody restored is not a backup.

## 6. API keys

- Make a key: `fdeops keys create --name <name> --role <role> --tenant <tenant>`. The command shows the key one time. The database keeps only its hash.
- Rotate a key: make the new key, change the client, then revoke the previous key with `fdeops keys revoke`.
- A key that leaked: revoke it immediately. Then read the audit log of the tenant.

## 7. Problems and what to do

| symptom | cause | what to do |
|---|---|---|
| `/ready` gives 503 | The database does not answer, or a folder is missing | Read the `checks` field of the response. |
| Many HTTP 429 responses | A client sends too many requests | Find the key in the logs. Change the limit only after a review. |
| Jobs stay `queued` | No worker operates | Start a worker. Read its log. |
| Jobs stay `running` | A worker stopped during a job | Wait for the lease to expire. A different worker then runs the job. |
| Many failed jobs | A model provider or a tenant file has a problem | Read the `error` field of the job. |

## 8. Incidents

1. Find the severity:
   - **Critical**: a tenant can see the data of a different tenant, or money moves incorrectly.
   - **High**: the API or the worker does not operate.
   - **Low**: one function does not operate.
2. For a critical incident, stop the cause first. For example, revoke a key, or roll back the agent release.
3. Write the times and the tasks in the incident record.
4. After the incident, write a postmortem. Use the [generated postmortem](../portfolio/generated/postmortem-ledgerloop-refund-window-drift.md) as the example.

## 9. A tenant stops its contract

1. Export the data that the tenant requests.
2. Make a backup.
3. Delete the data: `fdeops db purge-tenant <tenant> --confirm <tenant>`. The command deletes the rows, the keys, the jobs and the artifact files of that tenant only.
4. Remove the tenant folder from `tenants/`.
