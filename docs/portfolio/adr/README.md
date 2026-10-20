# Architecture Decision Records

*Language: ASD-STE100. Refer to the [glossary](../../glossary.md).*

Each record tells the context, the decision, the alternatives and the results of one decision. A new decision that changes a previous decision gets a new record. It does not change the previous record.

| number | decision | status |
|---|---|---|
| [0001](0001-python-stack-and-sync-core.md) | Python, Pydantic and a synchronous core | accepted |
| [0002](0002-record-and-replay.md) | Record and replay of each model call, with free models only | accepted |
| [0003](0003-postgres-job-queue.md) | A job queue in Postgres, not Celery and Redis | accepted |
| [0004](0004-own-retrieval-and-statistics.md) | Our own BM25, embedder and statistics | accepted |
| [0005](0005-gates-on-confidence-limits.md) | Release gates on confidence limits | accepted |
| [0006](0006-confirmed-only-by-intervention.md) | A cause is confirmed only by an intervention | accepted |
| [0007](0007-monitor-without-oracle.md) | A production monitor without an oracle | accepted |
| [0008](0008-static-web-export.md) | A static web UI from an export | accepted |
