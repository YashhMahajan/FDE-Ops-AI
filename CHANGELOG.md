# Changelog

All entries use ASD-STE100. Refer to the [glossary](docs/glossary.md).

## 2.0.0 (2026-10-20)

Version 2.0 completes milestones M0 to M10. All results have the label `pipeline-test` until real model runs (M11).

### Production monitor without an oracle

- `fdeops monitor` compares a current window of traffic with a reference window. It uses only signals that a live deployment can see: guardrail flags, superseded knowledge in the context, escalations, tool errors, episode errors, latency and tokens.
- Each tenant has `monitors.yaml`. Each monitor has a tolerance, a direction, a severity and an explanation.
- An alert needs all of the 95% interval of the change to be more than the tolerance. Rates use the Newcombe interval. Values use a bootstrap interval of the ratio.
- A Bernoulli CUSUM in ticket order tells how many tickets go by before the alarm.
- In the simulation, the report measures the precision and the recall of each signal, and the silent failures. It gives a review sample size for the silent failures.
- The flagship demo has a monitor step. In the drift incident, superseded context gives the first alarm after one ticket. The critical flags come after about 50 tickets. After the fix, the monitor gives no alerts.
- *What this shows:* the platform finds a production failure without the correct answers, and it tells which failures it cannot see.

### M10: Deployment kit and portfolio documents

- Docker images for the API, the worker and the web UI. Compose with Postgres (pgvector), the API and two workers. A CI job starts the stack and runs a job through it.
- `render.yaml` for free Render plans, and a Pages workflow that runs only when a person starts it.
- `fdeops regress` replays cassettes and compares each check with a minimum quality. CI runs it, and it skips a check that has no cassette.
- A kit for real model runs at no cost: `scripts/record_openrouter.sh` for free OpenRouter models, and a Kaggle notebook that serves an open model with vLLM.
- `fdeops portfolio` writes the postmortem, the benchmark report, the case study and the roadmap memos from the demo records.
- Written portfolio documents: the PRD, eight architecture decision records and the roadmap memo. The [portfolio index](docs/portfolio/README.md) connects each part of the mission to the code and the tests.
- The flagship incident of each tenant is in `tenant.yaml`. A test makes sure that no platform code names a tenant.

### M9: Web UI

- A static Next.js UI that reads the demo export. It needs no backend and no model.
- Pages: release log, release gates (an annunciator panel), monitor, comparisons (interval charts), traces (a drawer with the transcript, tool calls, spans and scores), diagnosis, roadmap and business value.
- CI builds the site and makes screenshots of each page on a desktop, on a phone and in dark mode.

### Documentation

- All documents use ASD-STE100 Simplified Technical English (issue 9).
- `fdeops docs check` finds the STE rules that a program can find: words that are not approved, sentence length, paragraph length, semicolons and contractions. CI runs it.
- The glossary gives the technical nouns and technical verbs of the project.

### M8: Business impact and product intelligence

- Each tenant has `costs.yaml`. Each value is an assumption with a low value, a likely value, a high value and a source.
- Measured outcomes for each cost category: automated, correctly escalated, failed and critical.
- A FAQ baseline without an LLM. The platform runs it as an external agent, thus its numbers are measured with the same rules.
- ROI with a Monte Carlo simulation. Each assumption comes from its range. Each measured rate comes from its posterior with partial pooling, thus a small category cannot invent a critical-error rate. The report gives percentiles and the probability that the savings are more than zero.
- Opportunities for each failure cluster: evidence, cost, fix, effort, confidence, and a score with its formula. Inconclusive items go to the list of items that we do not build.
- A roadmap memo with the three best items and the items that we do not build.
- Commands: `fdeops baseline`, `fdeops impact` and `fdeops opportunities`. API: `/impact` and `/opportunities` for each run.

### M7: Storage, API, jobs and authentication

- Database tables for runs, trials, annotations, audit events, API keys and jobs. The same code operates on SQLite (local) and Postgres (CI).
- An artifact store for run records, reports and diagnosis results. A key cannot go out of the store.
- A repository with a tenant scope. A request for the data of a different tenant gets "not found", also when the request uses the ID.
- API keys with four roles: viewer, engineer, approver and admin. The database keeps only the hash of each key.
- A job queue in the database with leases, retries and a worker. On Postgres, a claim uses `FOR UPDATE SKIP LOCKED`. A test makes sure that four workers at the same time do not get the same job.
- A FastAPI service: tenants, runs, reports, trials with traces, comparisons, diagnosis results, annotations, judge calibration, the audit log and releases (approve and roll back). Each log line is JSON with a request ID.
- Commands: `fdeops serve`, `fdeops worker`, `fdeops keys` and `fdeops db init`.
- CI runs the storage and queue tests on Postgres in a service container.

### M6: Releases, gates and the improvement loop

- A release is a frozen bundle: the agent configuration, the KB hash, the gate dataset and the gate configuration. Its hash identifies it.
- Each tenant has `gates.yaml`. Each gate must have an explanation, or the file does not load. Ledgerloop and Parcelpoint have different gates.
- Gates use confidence limits. These are the gates:
  - task success, critical violations and non-inferiority for each important slice,
  - p95 latency and cost for each resolution,
  - the integration suite, the regression suite, judge calibration and PII redaction.
- A gate that the platform cannot measure fails, unless the configuration accepts it.
- The integration suite runs sets of faults on a sample. It checks that no episode stops with an error, that no task occurs two times, and that each audit chain is correct. It found a real defect: data exports did not use idempotency keys. Plan changes also have records and idempotency keys at this time.
- A release registry on disk: propose, approve, reject, roll back and history. Only a person with an approver role can move production.
- Shadow mode runs a candidate next to production on the same traffic.
- The improvement loop selects a fix on the dev split and validates it on the test split. It stops at a decision that waits for approval. The approval adds the incident cases to the regression suite.
- New commands: `fdeops release`, `fdeops improve` and `fdeops shadow`. Each decision has a memo.
- *What this shows:* the full loop from incident to approved fix, with evidence at each step and a person at the last step.

### M5: Integrations and a second tenant

- A second fictional tenant, Parcelpoint (shipping SaaS), on the same platform. It has a new logistics pack with 11 scenarios: shipment tracking, late shipments, address changes, claims, legal risk, identity and injection. The policy, the risk tolerance, the scopes and the PII rules are different from Ledgerloop. Parcelpoint has its own drift: the claim limit changed from $500 to $300.
- Ingest of business data: validation, normalization and reference checks, with a data-quality report. The ingest step isolates bad records and tells the record, the field and the cause. Tenant worlds and case fixtures use it.
- PII redaction (email, card, phone and tenant patterns such as addresses). It occurs after the scores, thus the scores use the real text and the stored runs keep no PII.
- Incidents as YAML files. An incident run keeps the base dataset hash, thus a paired comparison with the baseline is correct. These are the seven incident types:
  - API faults, document drift and data quality,
  - prompt injection in tickets or in the KB,
  - model changes, retrieval changes and tool schema changes.
- An adapter for external Python agents (`ToolBox`, `--external file.py:function`). External agents use the same connector stack and the same evaluators.
- A REST connector that a YAML file configures, with field maps, typed HTTP errors, idempotency headers and secrets from the environment.
- *What this shows:* a new tenant needs configuration and, for a new domain, one pack. Dirty data, outages and injected text give reports, not failures.

### M4: Diagnosis

- A deterministic classifier gives each failed trial a primary failure class from a fixed taxonomy of 14 classes. A causal sequence selects the class, and each label has evidence (spans, violations, stale chunks, scores).
- Each domain pack tells which policy rules each KB section controls. Thus, the classifier links a violation to stale knowledge only when the stale section controls the violated rule.
- Clusters by class and scenario, with tag counts and examples.
- Counterfactual interventions from a playbook. Each intervention reports a fix rate and a regression rate on control cases, with intervals. These are the interventions:
  - a freshness filter, and an index with only the current sections,
  - oracle retrieval (diagnostic only), lexical retrieval and a larger top-k,
  - an enforced guardrail, more retries and a larger step budget.
- Verdicts: `confirmed by intervention`, `supported by evidence` or `inconclusive`. Interventions use the dev split. The test split needs `--allow-test`.
- `fdeops diagnose` writes `diagnosis.md` and `diagnosis.json`. Comparisons also show results for each tag. Run reports show the minimum detectable effect.
- Generated reports obey ASD-STE100, and a test checks them.
- A fix: `content_hash` of datasets and agent configurations was cached. A copy with `model_copy` kept the previous hash. At this time, the code calculates the hash each time.
- *What this shows:* the platform finds the stale-knowledge cluster of the drift incident, confirms the cause by intervention (7 of 7 cases fixed, 0 of 20 control cases broken), and recommends the freshness filter.

### M3: Evaluation engine

- Deterministic evaluators compare each episode with the oracle and with the world-state diff. They measure outcome, tool use, policy, escalation, retrieval, facts, injection, clarification and performance.
- LLM judges measure groundedness and communication. A judge that does not give a usable answer gives "no verdict". It does not give a pass.
- Calibration compares judge labels with human labels (Cohen's κ, with a minimum).
- Statistics: Wilson intervals, intervals and paired comparisons at case level, exact sign tests, Holm correction, pass^k, the rule of three and power calculations.
- The runner, Markdown reports with a provenance label, run comparison, and the commands `fdeops run`, `fdeops report` and `fdeops compare`.
- *What this shows:* the platform finds a regression from a stale index, finds the scenario that has the regression, and reports the uncertainty correctly.

### M2: Agent, models and integration layer

- A client for the OpenAI-compatible protocol with free presets (OpenRouter, vLLM, Ollama), a wait-and-retry wrapper for HTTP 429, and record and replay cassettes.
- Traces, and retrieval with BM25, a hashing embedder, hybrid fusion and a freshness filter.
- Resilient connectors. An operation that changes data occurs only one time, also after a retry. There is also a permission guard, an audit chain, fault injection and a policy monitor.
- The reference support agent and the episode runner. A rule-based model for pipeline tests.

### M1: Simulated customer world

- A versioned knowledge base, the billing domain pack, the policy oracle, 12 scenarios, versioned datasets and the Ledgerloop tenant.

### M0: Foundations

- Tools, the CI configuration and the core primitives.
