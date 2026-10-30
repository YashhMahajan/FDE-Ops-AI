# Changelog

## 2.2.0 (2026-10-30)

Use the platform on your own workflow. Version 2.1 was a platform that engineers could read and run on the fictional tenants. Version 2.2 gives an engineer the steps to make a tenant for a new company and to test an agent of their own.

### New

- `fdeops init DIR --pack billing|logistics --name "Company"` makes a starter tenant: policy, knowledge base, gates, monitors and datasets. The command checks the ID and refuses a folder that has files. It loads the new tenant to make sure that it is correct. It writes an agent configuration when the folder `configs/agents` is there. The starter files are part of the package (`fdeops/templates`), thus the command also operates after `pip install`.
- `fdeops doctor [--tenant DIR]` checks Python, the service dependencies, the model key, Docker, the data folder and a tenant. It does not print a key.
- `examples/agents/careful_refunder.py`: an example external agent that reads the refund window from the current knowledge-base section, ignores superseded text, and escalates large refunds. On the 51 dev cases of the fictional tenant Ledgerloop, it moves the success rate from 21.6% (95% CI 12.5% to 34.6%) to 78.4% (95% CI 65.4% to 87.5%). The trials with a critical violation go from 33 to 0. The paired difference is +56.9 points (95% CI +43.1 to +70.6), with 29 cases better and 0 cases worse. The label of these results is `measured-in-simulation`.
- Guides: a [quickstart](docs/guides/quickstart.md) and [test your own agent](docs/guides/test-your-own-agent.md).

### Tests

- Tests for `init` (the two packs, folder and ID checks, no placeholders left) and `doctor`. The suite has 428 tests.
- A test makes sure that the starter policy and knowledge base stay equal to the files of the demo tenant of the same pack.
- A test runs the two example agents and makes sure that the careful agent has no violations and the naive agent does not.

## 2.1.0 (2026-10-20)

Production readiness. A review against the usual defects of AI-made code found these items, and this version fixes them.

### Security

- Rate limits for each API key, a lower limit for requests that start work, and a limit on wrong keys for each client address. A limit gives HTTP 429 with `Retry-After`.
- Input rules: a pattern for tenant IDs, and maximum values for each number and text. Unknown fields are errors. The body size has a limit, and model settings have types.
- An unexpected error gives "internal error" and a request ID. The log keeps the stack trace. The response shows no internal data.
- Security headers on the API and on the web server. The web server operates without root rights.
- The API accepts connections only on `127.0.0.1` by default. Only the container uses `0.0.0.0`.
- Explicit checks replace `assert` in the code, because `python -O` removes assert statements. The linter has security rules.

### Operations

- Database migrations with Alembic. The service migrates at start with a lock. A test makes sure that the migrations make the same schema as the models.
- `GET /ready` examines the database and the folders. `GET /metrics` gives Prometheus metrics (admin key).
- The worker completes its current job before it stops on SIGTERM.
- Pagination on the lists of runs and audit events.
- `fdeops db upgrade`, `fdeops db revision` and `fdeops db purge-tenant` (all data of a tenant, for a tenant that stops its contract).
- The service examines its settings at start and stops with a clear message.
- A runbook, a configuration reference, a threat model, and a document about data and privacy.

### Supply chain and quality

- Each third-party CI step has a fixed commit hash, and CI has read-only rights.
- CI checks secrets in the full git history, known vulnerabilities (Python and web), dependency licenses and declared dependencies.
- A release workflow builds the package, an SBOM and checksums for each version tag.
- Weekly dependency update requests.
- The web dependencies use a fixed PostCSS version without known vulnerabilities.
- Tests that could not fail are exact at this time. A test makes sure that the glossary and the word list of the document check agree.
- A minimum test coverage of 90%.
- A CI job runs each command in the README and the guides, and examines each link.
- The web UI has a page for a missing address, a page for an error, a skip link and accessibility checks (WCAG 2.1 AA) on each page.
- Accessibility corrections: the text contrast is 4.5:1 or more in the two themes. The gate lamps are buttons in a list. A keyboard can scroll each wide table.
- LICENSE, SECURITY.md, CONTRIBUTING.md and `.env.example`.

## 2.0.0 (2026-10-20)

Version 2.0 completes milestones 0 to 10. All results have the label `pipeline-test` until real model runs (milestone 11).

### Production monitor without an oracle

- `fdeops monitor` compares a current window of traffic with a reference window. It uses only signals that a live deployment can see: guardrail flags, superseded knowledge in the context, escalations, tool errors, episode errors, latency and tokens.
- Each tenant has `monitors.yaml`. Each monitor has a tolerance, a direction, a severity and an explanation.
- An alert needs all of the 95% interval of the change to be more than the tolerance. Rates use the Newcombe interval. Values use a bootstrap interval of the ratio.
- A Bernoulli CUSUM in ticket order tells how many tickets go by before the alarm.
- In the simulation, the report measures the precision and the recall of each signal, and the silent failures. It gives a review sample size for the silent failures.
- The flagship demo has a monitor step. In the drift incident, superseded context gives the first alarm after one ticket. The critical flags come after about 50 tickets. After the fix, the monitor gives no alerts.
- *What this shows:* the platform finds a production failure without the correct answers, and it tells which failures it cannot see.

### Milestone 10: Deployment kit and portfolio documents

- Docker images for the API, the worker and the web UI. Compose with Postgres (pgvector), the API and two workers. A CI job starts the stack and runs a job through it.
- `render.yaml` for free Render plans, and a Pages workflow that runs only when a person starts it.
- `fdeops regress` replays cassettes and compares each check with a minimum quality. CI runs it, and it skips a check that has no cassette.
- A kit for real model runs at no cost: `scripts/record_openrouter.sh` for free OpenRouter models, and a Kaggle notebook that serves an open model with vLLM.
- `fdeops portfolio` writes the postmortem, the benchmark report, the case study and the roadmap memos from the demo records.
- Written portfolio documents: the PRD, eight architecture decision records and the roadmap memo. The [portfolio index](docs/portfolio/README.md) connects each part of the mission to the code and the tests.
- The flagship incident of each tenant is in `tenant.yaml`. A test makes sure that no platform code names a tenant.

### Milestone 9: Web UI

- A static Next.js UI that reads the demo export. It needs no backend and no model.
- Pages: release log, release gates (an annunciator panel), monitor, comparisons (interval charts), traces (a drawer with the transcript, tool calls, spans and scores), diagnosis, roadmap and business value.
- CI builds the site and makes screenshots of each page on a desktop, on a phone and in dark mode.

### Documentation

- `fdeops docs check` examines the text of the documents: the words, sentence length, paragraph length, semicolons and contractions. CI runs it.
- The glossary gives the technical nouns and technical verbs of the project.

### Milestone 8: Business impact and product intelligence

- Each tenant has `costs.yaml`. Each value is an assumption with a low value, a likely value, a high value and a source.
- Measured outcomes for each cost category: automated, correctly escalated, failed and critical.
- A FAQ baseline without an LLM. The platform runs it as an external agent, thus its numbers are measured with the same rules.
- ROI with a Monte Carlo simulation. Each assumption comes from its range. Each measured rate comes from its posterior with partial pooling, thus a small category cannot invent a critical-error rate. The report gives percentiles and the probability that the savings are more than zero.
- Opportunities for each failure cluster: evidence, cost, fix, effort, confidence, and a score with its formula. Inconclusive items go to the list of items that we do not build.
- A roadmap memo with the three best items and the items that we do not build.
- Commands: `fdeops baseline`, `fdeops impact` and `fdeops opportunities`. API: `/impact` and `/opportunities` for each run.

### Milestone 7: Storage, API, jobs and authentication

- Database tables for runs, trials, annotations, audit events, API keys and jobs. The same code operates on SQLite (local) and Postgres (CI).
- An artifact store for run records, reports and diagnosis results. A key cannot go out of the store.
- A repository with a tenant scope. A request for the data of a different tenant gets "not found", also when the request uses the ID.
- API keys with four roles: viewer, engineer, approver and admin. The database keeps only the hash of each key.
- A job queue in the database with leases, retries and a worker. On Postgres, a claim uses `FOR UPDATE SKIP LOCKED`. A test makes sure that four workers at the same time do not get the same job.
- A FastAPI service: tenants, runs, reports, trials with traces, comparisons, diagnosis results, annotations, judge calibration, the audit log and releases (approve and roll back). Each log line is JSON with a request ID.
- Commands: `fdeops serve`, `fdeops worker`, `fdeops keys` and `fdeops db init`.
- CI runs the storage and queue tests on Postgres in a service container.

### Milestone 6: Releases, gates and the improvement loop

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

### Milestone 5: Integrations and a second tenant

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

### Milestone 4: Diagnosis

- A deterministic classifier gives each failed trial a primary failure class from a fixed taxonomy of 14 classes. A causal sequence selects the class, and each label has evidence (spans, violations, stale chunks, scores).
- Each domain pack tells which policy rules each KB section controls. Thus, the classifier links a violation to stale knowledge only when the stale section controls the violated rule.
- Clusters by class and scenario, with tag counts and examples.
- Counterfactual interventions from a playbook. Each intervention reports a fix rate and a regression rate on control cases, with intervals. These are the interventions:
  - a freshness filter, and an index with only the current sections,
  - oracle retrieval (diagnostic only), lexical retrieval and a larger top-k,
  - an enforced guardrail, more retries and a larger step budget.
- Verdicts: `confirmed by intervention`, `supported by evidence` or `inconclusive`. Interventions use the dev split. The test split needs `--allow-test`.
- `fdeops diagnose` writes `diagnosis.md` and `diagnosis.json`. Comparisons also show results for each tag. Run reports show the minimum detectable effect.
- A test examines the text of the generated reports.
- A fix: `content_hash` of datasets and agent configurations was cached. A copy with `model_copy` kept the previous hash. At this time, the code calculates the hash each time.
- *What this shows:* the platform finds the stale-knowledge cluster of the drift incident, confirms the cause by intervention (7 of 7 cases fixed, 0 of 20 control cases broken), and recommends the freshness filter.

### Milestone 3: Evaluation engine

- Deterministic evaluators compare each episode with the oracle and with the world-state diff. They measure outcome, tool use, policy, escalation, retrieval, facts, injection, clarification and performance.
- LLM judges measure groundedness and communication. A judge that does not give a usable answer gives "no verdict". It does not give a pass.
- Calibration compares judge labels with human labels (Cohen's κ, with a minimum).
- Statistics: Wilson intervals, intervals and paired comparisons at case level, exact sign tests, Holm correction, pass^k, the rule of three and power calculations.
- The runner, Markdown reports with a provenance label, run comparison, and the commands `fdeops run`, `fdeops report` and `fdeops compare`.
- *What this shows:* the platform finds a regression from a stale index, finds the scenario that has the regression, and reports the uncertainty correctly.

### Milestone 2: Agent, models and integration layer

- A client for the OpenAI-compatible protocol with free presets (OpenRouter, vLLM, Ollama), a wait-and-retry wrapper for HTTP 429, and record and replay cassettes.
- Traces, and retrieval with BM25, a hashing embedder, hybrid fusion and a freshness filter.
- Resilient connectors. An operation that changes data occurs only one time, also after a retry. There is also a permission guard, an audit chain, fault injection and a policy monitor.
- The reference support agent and the episode runner. A rule-based model for pipeline tests.

### Milestone 1: Simulated customer world

- A versioned knowledge base, the billing domain pack, the policy oracle, 12 scenarios, versioned datasets and the Ledgerloop tenant.

### Milestone 0: Foundations

- Tools, the CI configuration and the core primitives.
