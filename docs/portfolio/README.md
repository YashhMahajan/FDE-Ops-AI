# Portfolio Documents

These documents explain the product, its decisions and its results. The platform writes the documents in `generated/` from its own records. A person wrote the other documents.

| document | file | source |
|---|---|---|
| Product requirements (PRD) | [prd.md](prd.md) | written |
| Architecture decisions (ADR) | [adr/](adr/) | written |
| Benchmark report | [generated/benchmark-report.md](generated/benchmark-report.md) | generated |
| Incident postmortem | [generated/postmortem-ledgerloop-refund-window-drift.md](generated/postmortem-ledgerloop-refund-window-drift.md) | generated |
| Customer deployment case study | [generated/case-study-parcelpoint.md](generated/case-study-parcelpoint.md) | generated |
| Roadmap memo | [roadmap-memo.md](roadmap-memo.md) and [generated/roadmap-ledgerloop.md](generated/roadmap-ledgerloop.md) | written and generated |

Make the generated documents again with this command:

```bash
uv run fdeops portfolio
```

## The mission and the evidence

The project brief gives one mission statement. The table divides it into eight parts, in the words of the brief.

For each part, the table gives the function, the code and the tests.

| part of the mission | what the platform does | where | test |
|---|---|---|---|
| "deploy AI agents into business workflows" | Tenants in configuration files. Connectors with retries, timeouts, rate limits, idempotency keys, permission checks and an audit chain. A REST connector from YAML. An adapter for external agents. An API with keys and roles, a job queue, Docker and Compose. | `tenancy`, `connectors`, `api`, `jobs`, `docker/` | `tests/connectors`, `tests/api`, `tests/jobs`, CI job `compose` |
| "evaluate their behavior" | Deterministic evaluators against an oracle, calibrated LLM judges, intervals, paired comparisons and slices. | `eval`, `fdeops run`, `fdeops compare` | `tests/eval` |
| "detect production failures" | A monitor with signals that a live deployment can see, without an oracle. Interval tests and a sequential detector. Shadow mode and an integration suite with faults. | `monitor`, `fdeops monitor`, `release.shadow`, `release.integration` | `tests/monitor`, `tests/release` |
| "diagnose root causes" | A failure taxonomy, clusters and counterfactual interventions. A cause is confirmed only by an intervention. | `diagnose`, `fdeops diagnose` | `tests/diagnose` |
| "improve performance" | An improvement loop that selects a fix on the dev split, validates it on the test split, and stops for a person to approve. | `improve`, `release.registry` | `tests/improve`, `tests/demo` |
| "without unacceptable cost" | A cost gate for each resolution, a token monitor, and ROI with its uncertainty against two baselines. | `release.gates`, `impact` | `tests/release`, `tests/impact` |
| "without unacceptable latency" | A p95 latency gate and a latency monitor. | `release.gates`, `monitor` | `tests/release`, `tests/monitor` |
| "without unacceptable risk" | Gates on confidence limits, critical-violation limits, non-inferiority for each slice, guardrails, PII redaction, approval by a person, rollback. | `release`, `connectors.guard`, `trace.redact` | `tests/release`, `tests/connectors`, `tests/trace` |

The flagship demo shows all parts in one run:

```bash
uv run fdeops demo --tenant tenants/ledgerloop
```
