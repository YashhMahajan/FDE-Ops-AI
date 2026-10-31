# Threat Model

## Assets

| asset | why it is important |
|---|---|
| The data of each tenant: runs, traces, annotations and the audit log | A tenant must not see the data of a different tenant. |
| API keys | A key gives access to the data and the tasks of its tenant. |
| Release decisions | A wrong release can put a bad agent into production. |
| Tool operations of the agent | A wrong refund moves money. |
| Model provider keys | A stolen key can cost money or show prompts. |

## Threats and controls

| threat | control | test |
|---|---|---|
| A key reads the data of a different tenant | The tenant guard on each route. The repository adds the tenant to each query. The response is 404, also when the data is there. | `test_cross_tenant_read_is_not_found` |
| A user with a low role approves a release | Roles on each route. Only the approver role can approve or roll back. | `test_viewer_cannot_start_runs_or_approve` |
| An attacker guesses API keys | Long random keys, a hash in the database, and a limit on wrong keys for each client address. | `test_wrong_keys_are_limited_for_each_client` |
| Too many requests stop the service | Rate limits for each key, a lower limit for requests that start work, and a limit on the body size. | `tests/api/test_hardening.py` |
| A path in a request reads files that are not in the permitted folders | Relative paths only, no `..`, a check of the resolved path, and a pattern for tenant IDs. | `test_bad_run_request_is_422_with_reason`, `test_bad_tenant_ids_are_not_found` |
| An error shows internal data | A general handler gives "internal error" and a request ID. The log keeps the stack trace. | `test_unhandled_error_is_500_without_internals` |
| Text in a ticket or in the knowledge base tells the agent to do a wrong task | The permission guard and the policy monitor operate on each tool call, not on the text. Injection scenarios are part of the datasets. | `tests/connectors`, the injection scenarios |
| Many clients make the rate counters use all memory | The table of counters has a limit of 10,000 entries. A client that the limiter refuses keeps its entry. | `tests/api/test_limiter_memory.py` |
| A service or a connector answers with an endless response | The REST connector stops at `max_response_bytes` (2 MB). | `tests/connectors/test_rest.py` |
| A long job runs two times, or a stale worker overwrites a result | A heartbeat extends the lease. Only the holder of the lease can save a result. | `tests/jobs/test_lease.py` |
| A default password stays in a deployment | Compose has no default password, and the ports use `127.0.0.1`. The containers have no capabilities and a read-only file system. | CI job `compose` |
| A crash gives a record file that has only half of its text | Record files use a unique temporary file, `fsync` and an atomic rename. | `tests/core/test_fsio.py` |
| A retry makes a refund two times | Idempotency keys on each operation that changes data. | `tests/connectors/test_resilience.py` |
| A dependency has a known vulnerability | Audits of the Python and web dependencies in CI, and weekly update requests. | CI job `security` |
| A secret goes into the repository | A check of the full git history in CI. Keys come only from the environment. | CI job `security` |
| A changed CI step from a third party runs bad code | Each third-party CI step has a fixed commit hash. CI has read-only rights. | `.github/workflows/` |

## Risks that stay

| risk | why we accept it at this time | what removes it |
|---|---|---|
| Rate counters are for each replica | One replica is sufficient for the load. | A limit in the reverse proxy, or a shared counter store |
| API keys have no expiry date | The number of keys is small, and a person can revoke each key. | An expiry date, and a reminder to rotate each key |
| No single sign-on | The users are engineers with keys. | OIDC for the web UI and the API |
| The artifact store is a local folder | One host is sufficient at this time. | An S3-compatible store with encryption |
| Free model providers can keep prompts | The data is fictional. | Self-hosted models or a provider contract for real data (refer to [data and privacy](data-and-privacy.md)) |
