# FDE-Ops-AI: System Design

*Status: approved. Version 2.0 contains milestones 0 to 10. This is a living document.*

## 1. Intent

FDE-Ops-AI is a platform that deploys AI agents into business workflows. It shows, with evidence, if an agent can go to production. It answers these questions:

- Does the agent do the task correctly in many representative cases and in adversarial cases?
- Does the agent obey the policies and permissions of this customer?
- When a document changes, an API stops or a model changes, can we find the problem, find the cause and prove the fix?
- Is a new release better than the current release by a margin that statistics can show?
- How much money and staff time does the agent save, compared with a specified baseline?
- What must the product team build next, and why?

### 1.1 The purpose of the project

The primary purpose is the flagship project of the author. The project teaches how teams build production AI systems. One product shows depth in three roles:

| Role | What the project shows |
|---|---|
| AI engineer | Evaluation science, agent and retrieval engineering, judge calibration, statistical comparison, traces |
| Forward deployed engineer (FDE) | Tenant onboarding, connectors that operate with bad APIs and bad data, permissions, audit, deployment |
| Product manager (PM) | Failures that become ranked opportunities with costs. Release decisions and ROI with their uncertainty. |

The secondary purpose has a lower priority. Developers can connect their own agents to the platform. This purpose controls the plug-in interfaces. It does not control the sequence of the work.

### 1.2 Differences from a usual evaluation dashboard

1. **A simulated customer world with a deterministic oracle.** The oracle calculates the ground truth from the policy and the data. An LLM does not write the answers.
2. **Fault injection for agents.** Incidents are declarative and have a seed. Examples are stale documents, API faults, prompt injection and model changes. A replay of each incident is possible.
3. **Diagnosis with counterfactual replay.** The platform runs the failed cases again with one change. It measures how many failures it fixes. A cause is *confirmed* only when an intervention shows it. Before that, the cause is a hypothesis.
4. **Release gates that use confidence limits.** A gate does not use a point estimate. Comparisons use paired data and non-inferiority tests.
5. **Record and replay of each model call.** Results are reproducible and cost nothing. This makes regression tests in CI possible.
6. **Each view helps a decision:** release or hold, fix this or that, build this or not.

## 2. Goals, non-goals and anti-goals

### 2.1 Goals

- One workflow from start to end: a customer-support agent for a B2B SaaS company. The agent finds accounts, does permitted tasks, uses the policy and escalates.
- Two fictional tenants on the same platform. They have different policies, gates and risk tolerances. No code is only for one tenant.
- Each result is reproducible from a commit hash, a dataset version and a cassette set.
- Each claim in the portfolio documents has a link to a run ID.
- The system is deployable (Docker, Compose, CI and deployment configurations). CI makes sure that it operates.

### 2.2 Non-goals

- Model training or fine-tuning.
- A general LLM framework, or a copy of each function of current observability products.
- Changes to production that the system makes without a person. The system proposes and validates. A person approves.
- Many agents only to have many agents.
- Kubernetes, service meshes or other infrastructure that the problem does not need.
- Real customer data.

### 2.3 Anti-goals (a failure, also when the code operates)

- Synthetic or simulated numbers that look like real customer results. Each report has a provenance label: `measured-in-simulation`, `estimated` or `pipeline-test`.
- LLM-judge scores without a calibration against human labels.
- A "root cause" that only a correlation supports.
- Views that only show charts and do not help a decision.
- A demo that operates only on the easy path and stops at a bad record or an HTTP 500 response.
- Thresholds that a person changes until the dashboard looks good. The tenant configuration and the PRD explain each gate.

## 3. Constraints

| Constraint | Result for the design |
|---|---|
| No paid LLM APIs (no OpenAI, no Anthropic) | Use **OpenRouter free models** (preferred) or open models on **free cloud GPUs** (vLLM in a Kaggle notebook). A cassette records each call. All other runs use replay. All providers use the OpenAI-compatible protocol, thus a change of provider is one configuration line. |
| No Docker and no long-running services on the Mac of the author (M2, 8 GB) | Local development uses **embedded storage (SQLite) and in-process components only**. Postgres, workers and the full stack operate in **GitHub Actions** service containers and in deployment targets. The Docker files are part of the product, and CI makes sure that they operate. |
| No fixed schedule. A thorough result is mandatory. | Work in milestones. Each milestone must be complete, with tests, before the next milestone starts. |
| Start with no code | Do not use code from other projects of the author. |

## 4. System overview

```
                         ┌──────────────────────────────────────────────┐
                         │                 Web UI (Next.js)             │
                         │ Release review · Runs · Traces · Diagnosis   │
                         │ Opportunities · ROI · Tenant setup           │
                         └───────────────▲──────────────────────────────┘
                                         │ REST (JSON)
┌──────────┐   ┌─────────────────────────┴───────────────────────────────┐
│   CLI    │──▶│              API (FastAPI) + job runner                 │
│ (Typer)  │   │      auth (API keys, roles) · tenancy guard · jobs      │
└──────────┘   └──┬──────────┬───────────┬───────────┬───────────┬───────┘
                  │          │           │           │           │
           ┌──────▼───┐ ┌────▼─────┐ ┌───▼──────┐ ┌──▼──────┐ ┌──▼────────┐
           │  Eval    │ │ Diagnose │ │ Improve  │ │ Release │ │ Impact &  │
           │  engine  │ │  engine  │ │  loop    │ │  gates  │ │ Insights  │
           └──────┬───┘ └────┬─────┘ └───┬──────┘ └──┬──────┘ └──┬────────┘
                  └──────────┴─────┬─────┴───────────┴───────────┘
                                   │ runs cases × trials
                         ┌─────────▼──────────┐
                         │  Agent runtime     │◀── external agent adapter
                         │  (system we test)  │     (HTTP or Python)
                         └──┬──────┬───────┬──┘
                            │      │       │
                  ┌─────────▼┐ ┌───▼─────┐ ┌▼────────────────────────┐
                  │ LLM layer│ │Retrieval│ │ Connectors (resilient)  │
                  │ record / │ │ BM25 +  │ │ timeouts·retries·breaker│
                  │ replay   │ │ vectors │ │ idempotency·audit·guard │
                  └──────────┘ └─────────┘ └───────────┬─────────────┘
                                                       │
                                  ┌────────────────────▼──────────────────┐
                                  │  Simulated customer world (per tenant)│
                                  │ versioned KB · accounts · billing ·   │
                                  │ tickets · policy engine · incidents   │
                                  └───────────────────────────────────────┘
  All layers: traces (OpenTelemetry GenAI names) · storage (SQLite or Postgres) · artifact store
```

### 4.1 Layer rule

Each layer imports only from the layers below it. An import-linter contract in CI makes sure of this:

`core → (llm, trace, retrieval, devtools) → world → connectors → packs → tenancy → agent → eval → (diagnose, monitor) → release → improve → impact → insights → storage → jobs → demo → api → cli`

The core library is **synchronous**. It uses thread pools for parallel trials. This keeps the agent loop and the tests easy to read and easy to debug. The API layer can serve requests at the same time (ADR-0003).

## 5. Components

### 5.1 `core`: domain model

All layers use typed Pydantic v2 models. Each ID is a ULID with a prefix (for example, `run_…` and `case_…`).

Datasets, prompts, agent configurations and releases are versioned objects. Each versioned object has a **content hash**: the SHA-256 of its canonical JSON. The same content always gives the same hash. This makes results reproducible.

### 5.2 `world` and `packs`: simulated customer world

The world is a deterministic simulation of a fictional SaaS company. Each tenant has its own world.

The world has two parts:

- A **generic engine** (`world`): entity state, diffs, the case and dataset model, the scenario framework and the user-simulator protocol.
- **Domain packs** (`packs/billing`, `packs/logistics`): entities, APIs, policy rules and scenario templates.

A tenant selects a pack and configures it. A new tenant in a current domain needs only configuration. A new domain needs a new pack, thus new code. This limit is intentional. The documents show it clearly, because it is part of the FDE story.

The world has these items:

- **Knowledge base.** Markdown documents with sections that have stable IDs. Each section has a **version and an effective date**. Thus, the platform can answer "what did the documents tell on date D", and it can find stale knowledge accurately.
- **Business data.** Customers, accounts, plans, invoices, payments, users and roles. A seed and a schema generate them.
- **APIs.** The APIs are in-process, and an HTTP version is optional. The APIs include billing (`get_invoice`, `issue_refund`, `change_plan`), accounts (`lookup_customer`) and tickets (`reply_to_customer`, `ask_clarifying_question`, `escalate_to_human`). Each API makes sure that the data stays correct. The APIs do not apply the business policy. The agent must obey the policy, and the policy monitor checks it.
- **Policy engine.** The tenant rules are in YAML (refund window, refund limit, roles that can request data exports). The **oracle** and the **policy monitor** use the same engine.
- **Case generator.** Scenario templates and seeded parameters make `Case` objects. Each case has the ticket text, hidden facts and **ground truth that the oracle calculates**. The deterministic user simulator uses the hidden facts to answer clarifying questions. The ground truth has these parts:
  - the necessary world-state changes (for example, "refund of 49.00 on inv_123"),
  - the tools that the agent must use and the tools that it must not use,
  - the facts that the reply must give, and the gold KB sections,
  - the facts that the reply must not give (for example, a superseded refund window),
  - slice tags (category, level of difficulty, adversarial, clarification).
- **Incidents.** Declarative YAML with a seed. These are the types: `doc_drift`, `api_fault` (timeout, 5xx, 429, malformed payload, expired credential), `prompt_injection`, `model_swap`, `retrieval_config_change`, `tool_schema_change` and `data_quality`.
- **User simulator.** It is deterministic. An LLM user simulator is a possible extension. It is off by default.

**Fictional tenants.** Each document identifies them as fictional.

| | **Ledgerloop** (subscription billing SaaS) | **Parcelpoint** (shipping and logistics SaaS) |
|---|---|---|
| Usual tickets | refunds, invoices, plan changes, failed payments, data export | shipment tracking, address change, damage claims, delivery windows |
| Risk tolerance | low (money moves) | moderate (latency is important, high volume) |
| Gates | lower confidence limit of task success ≥ 0.85, no critical violations, approval for refunds above $200 | lower confidence limit of task success ≥ 0.80, p95 latency budget, PII redaction is necessary |
| Escalation | each refund above the limit, each account-security request | claims above a value limit, legal or complaint words |

### 5.3 `llm`: model access with record and replay

- The `LLMClient` protocol has one method: `complete(request) -> response`.
- These are the providers. All of them are free:
  - `openai_compatible`: one client for the OpenAI-compatible protocol. It does not need an OpenAI account.
  - Presets: `openrouter` (free models, key from `OPENROUTER_API_KEY`, preferred), `vllm` (open models on a free cloud GPU) and `ollama`.
  - `RetryingLLM` waits and tries again when a free tier sends HTTP 429.
  - `scripted`: deterministic responses for unit tests.
  - `heuristic`: a rule-based model with seeded error modes. It tests the full pipeline without a GPU. **Each run with this model has the label `pipeline-test`. Do not use its numbers as a result.**
- **Cassettes** are JSONL files. The key of each record is `sha256(provider, canonical request)`. These are the modes:
  - `record`: call the provider and keep the response.
  - `replay`: give only the recorded responses. A missing record is an error.
  - `replay_or_record`: give the recorded response, or record a new one.
  - `live`: call the provider and record nothing.
- A replayed response keeps the initial latency and token usage. Thus, the performance metrics stay correct.

### 5.4 `retrieval`

- Chunks follow the sections. Each chunk keeps the document ID, section ID, version and effective dates.
- BM25 (our own code, short and easy to explain) and dense embeddings. These are the embedders:
  - `hashing`: deterministic vectors from feature hashing. It is lexical only and needs no download. Tests use it. Its label is "lexical baseline".
  - `sentence_transformers` and `fastembed`: optional extras with semantic models.
  - A cache keeps embeddings by content hash.
- Hybrid fusion (reciprocal rank fusion). An optional reranker interface.
- An optional freshness filter removes superseded versions at query time. The improvement loop can propose this fix.

### 5.5 `connectors`: integration layer

- The `Connector` protocol has two functions: `ops()` (tool schemas) and `call(op, args, ctx)`.
- `ResilientConnector` adds these functions to each connector:
  - a timeout for each operation,
  - retries with exponential backoff and jitter (only for errors that a retry can fix),
  - a circuit breaker and a token-bucket rate limit,
  - **idempotency keys** for operations that change data. Thus, a retry cannot refund two times.
  - typed errors that the agent can use.
- **Permission guard.** Before each call, the guard compares the scope of the operation with the scopes of the agent. A denial is a typed error, and the audit log records it.
- **Policy monitor.** It checks each operation against the policy before the operation occurs. In `observe` mode, it records violations. In `enforce` mode, it stops critical violations.
- **Audit log.** It is append-only. Each event has the hash of the event before it. Thus, a change to a previous event is easy to find.
- **PII redaction** occurs when the platform writes a trace. The tenant configuration controls it.
- **Data-quality report.** When the platform loads the business data of a tenant, it counts and isolates the records that have missing or incorrect fields. It does not remove bad records without a report.
- Connector types: world connectors (in-process and HTTP), and a generic REST connector with a field map.

### 5.6 `agent`: reference support agent (the system we test)

A small explicit workflow, not a framework:

`intake → retrieve → act (tool loop with a limit) → reply, clarify or escalate`

- Prompts are versioned files with content hashes.
- Limits: maximum tool calls, maximum tokens and maximum time.
- The agent gets tool errors as structured data. Then, it selects to try again, to send a question, or to escalate.
- **External agent adapter.** The platform can evaluate an agent that is a Python function or an HTTP endpoint. This is the entry point for developers.

### 5.7 `trace`: observability

- The span model uses the OpenTelemetry GenAI names (`gen_ai.*`) and our own `fdeops.*` names. These are the span types: agent, turn, LLM call, retrieval, tool call and guard.
- Each span records inputs, outputs, errors, latency, tokens and cost.
- Cost model: price tables for hosted models. For self-hosted models, the cost is GPU time multiplied by a rate for each hour. Its label is "estimate".
- Exporters: the database (default), JSONL and optional OTLP.

### 5.8 `eval`: evaluation engine

**Evaluators.** Use deterministic evaluators first. Use LLM judges only where a judgment is necessary.

| Layer | Evaluator | Method |
|---|---|---|
| Task success | `outcome` | Compare the world-state diff after the episode with the oracle diff. |
| Tool use | `tool_use` | The tools that the agent must use, the tools that it must not use, and argument errors. |
| Policy | `policy` | The violations that the policy monitor recorded. |
| Safety | `injection` | The agent did not do the tasks that injected text told it to do. |
| Escalation | `escalation` | The agent escalated only when the oracle tells it to. The report gives precision and recall. |
| Retrieval | `retrieval` | Recall, MRR and nDCG against the gold sections. Stale hits. |
| Knowledge | `facts` | The necessary facts are in the reply. Stale facts are not in the reply. |
| Groundedness | `judge.groundedness` | An LLM judge checks that the evidence supports each claim. |
| Communication | `judge.communication` | An LLM judge checks clarity, tone and completeness. |
| Performance | `perf` | Latency p50 and p95, tokens, cost for each case and for each resolution. |

**Datasets.**

- Each dataset has a version, a content hash and a provenance (generator version, template, seed).
- There are two splits. Use `dev` for diagnosis and tuning. Keep `test` for gates. The improvement loop can read only `dev`. Gates read only `test`. The code makes sure of this.

**Runs.** A run has cases × *k* trials for each configuration. Trials make reliability measurable.

**Statistics** (`eval.stats`):

- Wilson intervals for rates. A run can have more than one trial for each case. Then, the interval uses the number of cases as the sample size, because trials of one case are related.
- Paired bootstrap intervals at case level, for differences.
- Exact sign tests (McNemar) on cases with different results.
- pass^k: the probability that all k trials of a case succeed.
- Holm correction across slices.
- The rule of three gives a maximum limit when there are no events.
- Power calculations and the minimum detectable effect give the necessary dataset size.

**Judge calibration.** Persons label a sample of trials. The report gives Cohen's κ, a confusion matrix and the agreement for each slice. Pairwise judges run with a position swap to measure position bias. A judge with κ below the configured minimum cannot be part of a release gate.

### 5.9 `diagnose`: failure analysis

1. **Classify** each failed trial into a fixed taxonomy. Deterministic rules use the trace and the ground truth, and they give evidence (span IDs). These are the classes:
   `retrieval_miss` · `stale_knowledge` · `grounding_failure` · `wrong_tool` · `bad_arguments` · `permission_violation` · `policy_violation` · `unhandled_tool_error` · `timeout_or_budget` · `injection_followed` · `missed_escalation` · `over_escalation` · `clarification_failure` · `reasoning_error` (the remaining failures).
2. **Cluster** the failures by class, scenario and tag. Each cluster has a count and the business volume that it touches.
3. **Make hypotheses** for each cluster from a playbook. For example, stale knowledge can come from document freshness, the index version or the prompt.
4. **Intervene.** Replay the cases of the cluster with one change. Possible changes are oracle retrieval, a previous document, prompt or model, a different top-k, or a tool validator. Each intervention reports a fix rate with an interval, and a regression rate on the cases that passed.
5. **Give a verdict.** Use only these words: `confirmed by intervention`, `supported by evidence` or `inconclusive`.

### 5.9.1 `monitor`: production monitoring without an oracle

Production traffic has no oracle. Thus, the monitor uses only signals that a live deployment can see (ADR-0007). Examples are guardrail flags, superseded knowledge in the context, escalations, tool errors, latency and tokens.

1. **Compare two windows.** A reference window (for example, the release run) and a current window of traffic.
2. **Test each monitor.** A rate uses the Newcombe interval of the change. A value uses a bootstrap interval of the ratio. An alert occurs only when all of the interval is more than the tolerance in `monitors.yaml`.
3. **Find the alarm ticket.** A Bernoulli CUSUM in ticket order tells how many tickets go by before the alarm.
4. **Measure the monitor.** In the simulation, the oracle is known. The report gives the precision and the recall of each signal, the silent failures and a review sample size.

An alert is a symptom, not a cause. The next step is the diagnosis on the dev split.

### 5.10 `improve`: closed improvement loop

Find → find the cause → **recommend** → **validate** → **release or reject**.

- A recommendation is a specified change to the agent configuration, with its expected effect and its trade-offs.
- Validation is an experiment on `dev`, then a gate run on `test`.
- A change to production needs an `ApprovalRecord` from a user with the `approver` role. No change occurs automatically.

### 5.11 `release`: releases and gates

- A `Release` is an immutable bundle hash: model, prompt, retrieval configuration, tools, dataset version and gate configuration.
- Each tenant has gates in YAML. Each gate has an explanation:
  - task success: the **lower confidence limit** must be at or above the threshold,
  - critical violations: the run must have no violations, and the rule-of-three maximum limit must be at or below the gate value,
  - non-inferiority against the current production release on the important slices (margin δ),
  - p95 latency and cost for each resolution must be in the budget,
  - judge calibration κ must be at or above the minimum (if a judge is part of a gate),
  - the integration tests must pass.
- The output is a `ReleaseDecision` record (the result and evidence for each gate, the approver and the time) and a decision memo in Markdown.
- A rollback moves the `production` pointer of the tenant to the previous release. Shadow mode runs the candidate on recorded production traffic without side effects.

### 5.12 `impact`: business impact and ROI

- Each tenant has a cost model with these items:
  - the time that a person needs for one ticket of each category, and the cost of staff for each hour,
  - the review cost and the cost of a critical error,
  - the model cost, the infrastructure cost, and the integration and maintenance cost.
- Baselines: human only, and a simple baseline without an LLM (a retrieval-only FAQ responder). The LLM agent must be better than this baseline.
- Outputs: automation rate, escalation rate, cost for each correct resolution, net savings and the break-even volume. A **Monte Carlo simulation of the assumptions** gives the uncertainty. Each number has the label "measured" or "assumption".

### 5.13 `insights`: product intelligence

- The platform puts failure clusters, impact and experiment results together into **opportunities**. Each opportunity has these items:
  - the problem, with evidence (links to runs and traces),
  - the proportion of the cases that have the problem, the severity and the cost of the problem,
  - the estimated effort (a person gives it),
  - the confidence of the diagnosis,
  - the expected benefit (fix rate from the interventions × volume × cost),
  - a validation plan.
- The rank formula is expected value ÷ effort, weighted by confidence. The UI shows the formula, and you can examine each input.
- The platform writes a roadmap memo. The memo also tells what not to build, and why.

### 5.14 `tenancy`: multi-tenant configuration

- Each tenant is configuration as code: `tenants/<id>/tenant.yaml`, a policy file, KB documents, dataset specifications, gates and a cost model.
- Each database row has a `tenant_id`. The repository layer applies a tenant scope, and tests look for data that goes to the wrong tenant.
- A new tenant needs configuration only. The platform measures and reports the time to onboard a tenant (an FDE metric).

### 5.15 `storage`, `api`, `jobs` and `cli`

- **Storage.** SQLAlchemy 2.0. SQLite locally, and Postgres in CI and deployments. Large items (traces, cassettes, reports) go into an artifact store interface: the local file system or an S3-compatible store.
- **API.** FastAPI with OpenAPI documents. API keys are hashed and have scopes. These are the roles: `viewer`, `engineer`, `approver` and `admin`.
- **Jobs.** An in-process runner locally. In deployments, a queue in Postgres (`FOR UPDATE SKIP LOCKED`) replaces Celery and Redis. Thus, there is one less service. An ADR records this trade-off.
- **CLI.** `fdeops` (Typer). Each function is available in the CLI before the UI has it.

### 5.16 `web`: user interface

Next.js and TypeScript. Each view answers one decision:

| View | Decision |
|---|---|
| Release review | Do we release this candidate? |
| Run comparison | Is B better than A, where, and how sure are we? |
| Trace explorer | What occurred in this case? |
| Diagnosis | Why does this cluster fail, and which cause is confirmed? |
| Opportunities | What do we build next? |
| ROI | Is this deployment worth its cost, and with which assumptions? |
| Tenant setup | Is the configuration of this customer complete and correct? |

A **static demo build** reads exported JSON snapshots. Thus, a public demo needs no backend and no model.

### 5.17 Infrastructure and deployment

- Python 3.11 or a subsequent version, with `uv`. Tools: ruff, mypy (strict for `core` and `eval`), pytest, import-linter and the document checker.
- Dockerfiles for the API, the worker and the web UI. A `docker-compose.yml` for the full stack (API, worker, Postgres with pgvector, web UI).
- GitHub Actions:
  - lint, types, document checks and tests for each push,
  - integration tests against a Postgres service container,
  - an **evaluation regression job** that replays cassettes. The job stops the pull request if a gate has a regression.
  - a smoke test of the Compose stack.
- **Cloud recording kit.** A Kaggle notebook and a script. They start vLLM with an open 7B to 8B instruct model, run `fdeops run --llm-mode record`, and put the cassettes and results into an archive for download.
- Deployment configurations for one free or low-cost target, and the static demo.

## 6. Main flows

### 6.1 Evaluation run

`fdeops run --tenant tenants/ledgerloop --agent configs/agents/ledgerloop-v1.yaml --dataset data/datasets/ledgerloop/support-core@v1 --split test --trials 3 --llm-mode replay`

The run does these steps:

1. It makes a run record.
2. For each case and trial, it makes a new copy of the world and runs the agent.
3. It records the trace and the world state at the end.
4. It runs the evaluators and calculates the scores and statistics.
5. It writes a report (JSON and Markdown) with a provenance label.

### 6.2 The flagship demo

1. Release `v1` is in production for Ledgerloop.
2. Incident: the refund window changes from 30 days to 14 days (`doc_drift`). The stale section stays in the index.
3. The monitoring run shows a decrease in task success on the `refund` slice. The paired test shows that the decrease is real.
4. Diagnosis puts the failures in the `stale_knowledge` cluster. These are the interventions:
   - "previous document version" removes the failures. This confirms the cause.
   - "freshness filter" fixes most failures with no regressions.
   - "larger model" fixes fewer failures at a higher cost.
5. The improvement loop proposes `v2`: the freshness filter and a reindex job. The experiment runs on `dev` and the gate run uses `test`. The gates pass, the approver signs, `v2` goes to production and the platform adds a regression test case.
6. ROI and opportunities change. "Retrieval freshness" has a higher rank than "model upgrade" for expected value for each unit of effort.
7. The platform writes the postmortem from the run records.

(The numbers in step 4 come from recorded runs, not from this document.)

## 7. Portfolio documents

The platform generates these documents from real run data where possible:

1. PRD: user, problem, workflow, non-goals, metrics and risks.
2. ADRs: one for each important decision.
3. Benchmark report: dataset method, baselines, metrics with intervals, ablations, failure classes and limits.
4. Incident postmortem (from the demo).
5. Customer deployment case study: a simulated discovery and onboarding of Parcelpoint. Its label is "simulated".
6. Roadmap memo: the three most valuable improvements, their expected effect and cost, dependencies, and what we do not build.

## 8. Requirements traceability

This matrix connects each requirement of the project brief to the part of the system that satisfies it.

| Requirement in the brief | Where the system satisfies it | Milestone |
|---|---|---|
| 1. Evaluation engine: task success, groundedness, retrieval, tool use, policy, safety, reliability, performance | `eval.evaluators`, `eval.judges`, pass^k in `eval.stats` | Milestone 3 |
| Versioned datasets with provenance and train/test separation | `world.dataset` (content hash, dev/test split, split guard) | Milestones 1 and 6 |
| Hard, adversarial and realistic edge cases | 12 billing scenarios (injection, drift, permission, clarification) and the logistics pack | Milestones 1 and 5 |
| Pairwise comparisons and slices | `eval.compare` (case level, Holm) | Milestone 3 |
| Judge calibration against human labels | `eval.calibration`, annotation command | Milestones 3 and 7 |
| Confidence intervals and significance | `eval.stats` | Milestone 3 |
| Regression tests on each change | evaluation regression job with cassette replay in CI | Milestone 10 |
| 2. Traces with context, documents, prompt and model versions, tool calls, decisions, output, feedback, latency, tokens, cost | `trace`, `agent.episode`, `eval.report` | Milestones 2 and 3 |
| Failure taxonomy and root-cause workflow | `diagnose` | Milestone 4 |
| Hypotheses, not certainty | verdict words in `diagnose` | Milestone 4 |
| 3. Closed loop: find, find the cause, recommend, validate, release or reject | `improve` with approval records | Milestone 6 |
| 4. Connector architecture: ticketing, knowledge base, business data | `connectors`, `packs` | Milestones 2 and 5 |
| Tenant configuration and isolated data | `tenancy`, tenant scope in `storage` | Milestones 1 and 7 |
| Authentication and permission-aware tool calls | API keys and roles, `connectors.guard` | Milestones 2 and 7 |
| Retries, timeouts, rate limits, idempotency | `connectors.resilience` | Milestone 2 |
| Structured logs, errors, audit trail | `connectors.audit`, structured logs in `api` | Milestones 2 and 7 |
| Local and container deployment, secrets, access control | Dockerfiles, Compose, settings from the environment | Milestones 7 and 10 |
| A path from prototype to a monitored pilot | shadow mode, release gates, the production monitor | Milestone 6, 2.0 |
| Detection of production failures without correct answers | `monitor` (signals that a deployment can see, interval tests, CUSUM, detection quality) | 2.0 |
| Broken API, missing fields, expired credentials, bad data | `connectors.faults`, data-quality report | Milestones 2 and 5 |
| 5. Releases that identify the model, prompt, retrieval, tools and dataset | `release.Release` bundle hash | Milestone 6 |
| Gates: success, no critical regressions, latency, cost, slices, integration tests | `release.gates` | Milestone 6 |
| Configurable gates with explanations | `tenants/*/gates.yaml` | Milestone 6 |
| Rollback, version comparison, decision record | `release` | Milestone 6 |
| 6. Business impact: success, escalation, time for each ticket, cost for each resolution, critical errors, adoption, integration time | `impact` | Milestone 8 |
| ROI against a baseline, measured compared with estimated | `impact` (Monte Carlo, provenance labels) | Milestone 8 |
| 7. Multi-tenant: knowledge, rules, datasets, models, cost and latency limits, escalation, release needs | `tenancy`, Ledgerloop and Parcelpoint | Milestone 5 |
| Two customers with different policies and risk tolerance | Ledgerloop and Parcelpoint | Milestone 5 |
| 8. Product intelligence: ranked opportunities with evidence and confidence | `insights` | Milestone 8 |
| Prioritized roadmap with evidence | roadmap memo generator | Milestone 8 |
| Architecture: web app, API, jobs, evaluation, observability, integrations, optimization, data | sections 4 and 5 | Milestones 7 to 10 |
| PostgreSQL, pgvector, background workers, Docker, CI/CD | `storage`, Postgres queue, Compose, GitHub Actions | Milestones 7 and 10 |
| Six portfolio documents | `docs/portfolio/` | Milestones 10 to 12 |
| Demo: regression, diagnosis, fix, release through gates, impact analysis | `fdeops demo` and section 6.2 | Milestones 6 to 10 |
| Do not: many agents, chart-only views, judges without validation, benchmark-only optimization, generic multi-tenancy before the workflow operates, production claims without proof | section 2.3 and the gate rules | all |

## 9. Milestones

Each milestone ends with tests that pass and a short "what this shows" note in the release notes.

| # | Milestone | External resources |
|---|---|---|
| Milestone 0 | Repository foundations: tools, CI configuration, core models, hashes, configuration loading | No |
| Milestone 1 | Simulated world: KB, data, APIs, policy engine, oracle, case generator, datasets | No |
| Milestone 2 | LLM layer, retrieval, resilient connectors, reference agent, traces | No |
| Milestone 3 | Evaluation engine: evaluators, runner, statistics, reports | No |
| Milestone 4 | Diagnosis: taxonomy, clusters, counterfactual interventions | No |
| Milestone 5 | Executable incidents, PII redaction, data-quality report, logistics pack and Parcelpoint | No |
| Milestone 6 | Releases, gates, improvement loop, approvals, rollback, shadow mode | No |
| Milestone 7 | Storage (SQLite and Postgres), API, jobs, authentication, tenant scope | No (CI tests Postgres) |
| Milestone 8 | Impact and ROI, insights and opportunities | No |
| Milestone 9 | Web UI and static demo export | No |
| Milestone 10 | Docker, Compose, CI workflows, Kaggle kit, deployment configurations, portfolio documents | Written locally. CI and Kaggle run them. |
| Milestone 11 | Real recorded runs, benchmark report with real numbers | **Yes** (OpenRouter free models or Kaggle GPU) |
| Milestone 12 | Public deployment and demo | **Yes** (GitHub, hosting) |

Status at version 2.0 (2026-10-20): milestones 0 to 10 are complete. The production monitor (section 5.9.1) is also complete. Milestones 11 and 12 need the external resources in the table.

## 10. Test strategy

- **Unit tests** for each evaluator, statistics function, policy rule, resilience behavior (fake clock, injected faults) and cassette key. Statistics tests use known values.
- **Property tests** (Hypothesis): the oracle agrees with the policy engine for each generated world. Hashes do not change when keys change order.
- **Integration tests**: full episodes with the scripted or heuristic model through real connectors and the world. API tests with a test client. Postgres tests run only in CI.
- **Golden runs**: a small replay run whose summary must not change unless a person changes it.
- **Contract tests** for the external agent adapter.

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Small free models can be weak at tool use | Do a model-selection experiment first (milestone 11). The agent continues after errors. Weak models give useful failure data. Providers are pluggable. |
| The simulation is too clean | Incidents, data-quality faults, adversarial templates and a baseline without an LLM. Each report tells its limits. |
| Free quotas are small | Record one time, replay many times. The power calculator gives the dataset size. |
| The scope becomes too large | Milestone gates. Reviews check the non-goals. |
| Judges are not reliable | The calibration module. A judge below the κ minimum cannot be part of a gate. Deterministic evaluators are the base of the gates. |

## 12. Decisions for the builder

The builder selects libraries in the stack (for example, the embedding model and the chart library), the file structure in each package, the prompt text, the visual design and the first gate thresholds. The tenant configuration must explain each threshold.

## 13. Decisions that the assistant made (for review)

- Domain: B2B SaaS customer support. The tenants are Ledgerloop and Parcelpoint (fictional).
- A job queue in Postgres, not Celery and Redis.
- Our own BM25 and statistics code (with scipy for distributions), because this code teaches the methods. Mature libraries in other areas.
- Gates use lower confidence limits and non-inferiority, not point estimates.
- The `heuristic` model is only for pipeline tests. Its outputs have a label. Do not use them as a result.
- Design documents are in `docs/design/`, so that the repository is easy for reviewers to read.
