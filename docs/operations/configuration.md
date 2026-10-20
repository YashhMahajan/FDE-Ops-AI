# Configuration Reference

The service reads its settings from environment variables at start-up. It examines them before it accepts a request. A wrong setting stops the start with a message that names the setting. The file `.env.example` gives a template.

## Storage

| setting | default | function |
|---|---|---|
| `FDEOPS_DATABASE_URL` | `sqlite:///fdeops.db` | The database. Use Postgres in production. A `postgres://` URL from a host gets the correct driver name. |
| `FDEOPS_ARTIFACTS_DIR` | `artifacts` | The folder for run records, reports and diagnosis results. Back it up with the database. |
| `FDEOPS_REGISTRY_DIR` | `releases` | The folder of the release registry. Back it up with the database. |
| `FDEOPS_TENANTS_DIR` | `tenants` | The tenant folders. The start stops if the folder is missing. |
| `FDEOPS_CONFIGS_DIR` | `configs` | The agent configurations. The start stops if the folder is missing. |

## Protection of the API

| setting | default | function |
|---|---|---|
| `FDEOPS_CORS_ORIGINS` | empty | The web origins that can call the API, with commas between them. `*` is not permitted. |
| `FDEOPS_RATE_PER_MINUTE` | `120` | Requests for each API key in one minute. |
| `FDEOPS_EXPENSIVE_PER_MINUTE` | `10` | Requests that start work (a run, a diagnosis or an ROI calculation) for each API key in one minute. |
| `FDEOPS_AUTH_FAILURES_PER_MINUTE` | `10` | Requests with a missing or wrong key, for each client address in one minute. |
| `FDEOPS_MAX_BODY_BYTES` | `1000000` | The maximum size of a request body. A larger request gets HTTP 413. |

Each API replica keeps its own rate counters. With more than one replica, the real limit is the limit multiplied by the number of replicas. Use a limit in the reverse proxy for a strict global limit.

## Models

| setting | default | function |
|---|---|---|
| `OPENROUTER_API_KEY` | empty | The key for free OpenRouter models. Replay and the rule-based model do not need it. |
| `FDEOPS_LLM_API_KEY` | empty | The key for the `custom` provider, if the server needs a key. |

## Tests only

| setting | function |
|---|---|
| `FDEOPS_TEST_DATABASE_URL` | Runs the storage and queue tests on this database. CI uses it for Postgres. |
