# FDE-Ops-AI — System Design

*Status: approved direction, living document · Created 2026-10-18*

## 1. Intent

FDE-Ops-AI is a platform for **deploying AI agents into real business workflows and deciding, with evidence, whether they are good enough to ship.** It answers the questions that come after a demo works:

- Does the agent solve the task reliably across many representative cases, including adversarial ones?
- Does it follow *this* customer's policies and permissions?
- When something breaks — a document changes, an API fails, a model is swapped — can we detect it, find the cause, and prove the fix?
- Is a new release better than the current one, by a margin we can defend statistically?
- What is it worth in money and staff time, compared to an explicit baseline?
- What should the product team build next, and why?

### Why it exists

Primary purpose: the author's flagship project. It is meant to teach how production AI systems are built and to show, in one coherent product, depth across three roles:

| Role | What the project proves |
|---|---|
| AI Engineer | Evaluation science, agent and retrieval engineering, judge calibration, statistical comparison, tracing |
| Forward Deployed Engineer | Tenant onboarding, connectors that survive messy APIs and data, permissions, audit, deployability |
| Product Manager | Turning failures into prioritized, costed opportunities. Release decisions and ROI with honest uncertainty. |

Secondary purpose, lower priority: developers can point it at their own agents. That goal drives the plug-in interfaces. It does not set the order of work.

### What makes it different from "another eval dashboard"

1. **A simulated customer world with a deterministic oracle.** Ground truth comes from executing the tenant's policy against the world's state. No LLM writes the answer key.
2. **Chaos engineering for agents.** Incidents (stale docs, API faults, prompt injection, model swaps) are declarative and seeded, so every one can be replayed.
3. **Diagnosis by counterfactual replay.** Re-run failed cases with one component changed and measure how many get fixed. A cause counts as *confirmed* only when an intervention backs it up. Until then it is a hypothesis.
4. **Release gates that use confidence bounds, not point estimates.** Comparisons are non-inferiority tests on paired data.
5. **Record and replay for every model call.** Results are reproducible at zero cost, which makes regression testing in CI possible.
6. **Every view supports a decision**: ship or hold, fix this or that, build this or skip it.

## 2. Goals, non-goals, anti-goals

### Goals

- One complete workflow end to end: a customer-support agent for a B2B SaaS company. It looks up accounts, takes permitted actions, cites policy, and escalates.
- Two fictional tenants on the same platform with different policies, gates, and risk tolerance. No tenant-specific code.
- Every result reproducible from a commit hash, a dataset version, and a cassette set.
- Each claim in the portfolio artifacts traces back to a run ID.
- Ships as a deployable system (Docker, Compose, CI, deploy configs) that is verified in CI.

### Non-goals

- Training or fine-tuning models.
- A general LLM framework, or a feature-for-feature competitor to existing observability products.
- Autonomous production changes. The system proposes and validates. A human approves.
- Multi-agent orchestration for its own sake.
- Kubernetes, service meshes, or other infrastructure the problem doesn't need.
- Real customer data.

### Anti-goals (failure even if it "works")

- Synthetic or simulated numbers presented as real customer impact. Every report is labeled with its provenance: `measured-in-simulation`, `estimated`, or `pipeline-test`.
- LLM-judge scores reported without calibration against human labels.
- Calling a cause a "root cause" when only a correlation supports it.
- Views that are just charts, with no decision attached.
- A happy-path demo that falls over on a malformed record or a 500 response.
- Thresholds tuned until the dashboard looks good. Gates are justified in the tenant config and in the PRD.

## 3. Constraints

| Constraint | Consequence for the design |
|---|---|
| No paid LLM APIs | Open-weight models served on **free cloud GPUs** (e.g. Kaggle notebooks), with every call recorded to cassettes. Everything else replays. Providers stay pluggable, so a user with keys changes one line. |
| No Docker or long-running services on the author's Mac (M2, 8 GB) | Local development uses **embedded storage (SQLite) and in-process components only**. Postgres, workers, and the full stack run in **GitHub Actions** service containers and in deploy targets. Docker artifacts still ship and are verified in CI. |
| No fixed timeline, thoroughness is mandatory | Build in milestones. Each milestone must be complete and tested before the next starts. |
| Built from scratch | No reuse of the author's other projects. |

## 4. System overview

```
                         ┌──────────────────────────────────────────────┐
                         │                 Web UI (Next.js)             │
                         │ Release review · Runs · Traces · Diagnosis   │
                         │ Opportunities · ROI · Tenant config          │
                         └───────────────▲──────────────────────────────┘
                                         │ REST (JSON)
┌──────────┐   ┌─────────────────────────┴───────────────────────────────┐
│   CLI    │──▶│              API (FastAPI) + Job runner                 │
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
                         │  (system under test)│     (HTTP / Python / OTel)
                         └──┬──────┬───────┬──┘
                            │      │       │
                  ┌─────────▼┐ ┌───▼─────┐ ┌▼────────────────────────┐
                  │ LLM layer│ │Retrieval│ │ Connectors (resilient)  │
                  │ record / │ │ BM25 +  │ │ timeouts·retries·breaker│
                  │ replay   │ │ vectors │ │ idempotency·audit·perms │
                  └──────────┘ └─────────┘ └───────────┬─────────────┘
                                                       │
                                  ┌────────────────────▼──────────────────┐
                                  │  Simulated customer world (per tenant)│
                                  │ versioned KB · accounts · billing ·   │
                                  │ tickets · policy engine · incidents   │
                                  └───────────────────────────────────────┘
  Cross-cutting: tracing (OTel GenAI conventions) · storage (SQLite⇄Postgres) · artifact store
```

### Layering rule

Dependencies point one way only. `import-linter` enforces it in CI:

`core → (llm, trace, retrieval, world) → connectors → packs → tenancy → agent → eval → diagnose → (improve, release) → (impact, insights) → (api, cli)`

The core library is **synchronous** and uses thread pools for parallel trials. That keeps the agent loop and the tests simple to read and debug. The API layer can still serve requests concurrently. (ADR-0003.)

## 5. Components

### 5.1 `core` — domain model

Typed Pydantic v2 models shared by every layer. All IDs are prefixed ULIDs (`run_…`, `case_…`). Every versioned object (dataset, prompt, agent config, release) has a **content hash**: the SHA-256 of its canonical JSON. Identical content means an identical hash, so results can be reproduced.

Key entities: `Tenant`, `AgentConfig` (model, prompt version, retrieval config, tool set, limits), `Release` (frozen bundle of AgentConfig + dataset version + gate config), `Dataset` / `Case`, `Run` / `Trial`, `Trace` / `Span`, `Score`, `FailureLabel`, `Diagnosis`, `Experiment`, `GateResult`, `ReleaseDecision`, `Opportunity`, `ApprovalRecord`, `AuditEvent`.

### 5.2 `world` + `packs` — simulated customer world

A deterministic simulation of a fictional SaaS company. Each tenant has its own world.

The world is split into a **generic engine** (`world`: entity state and diffing, policy-engine base, case and dataset model, generator framework, user-simulator base) and **domain packs** (`packs/billing`, `packs/logistics`: entities, APIs, policy rules, scenario templates). A tenant picks a pack and configures it.
- A new tenant in an existing domain needs config only.
- A new *domain* needs a new pack, which means code.

That boundary is deliberate, and documenting it honestly is part of the FDE story.

- **Knowledge base**: markdown documents split into sections with stable IDs. Every section has a **version and effective dates**, so "what did the docs say on date D" has an answer, and stale knowledge can be detected exactly.
- **Business data**: customers, accounts, plans, invoices, payments, users, and roles. Generated by seed from a declared schema.
- **APIs** (in-process, plus an optional FastAPI HTTP facade for realism): billing (`get_invoice`, `issue_refund`, `change_plan`), accounts (`lookup_customer`, `get_user`), ticketing (`get_ticket`, `reply`, `escalate`, `set_status`). Each API checks permissions and records state changes.
- **Policy engine**: tenant rules in YAML (refund window, auto-refund limit, who may trigger data exports, what needs human approval). The same engine powers both the **oracle** and the **policy-compliance evaluator**.
- **Case generator**: scenario templates × seeded parameters → `Case` objects. Each case has the ticket text, hidden facts (used by the deterministic user simulator to answer clarifying questions), and **ground truth computed by the oracle**:
  - the expected final world state diff (e.g. "refund of 49.00 on inv_123", "ticket escalated with reason=over_limit"),
  - expected and forbidden tool calls,
  - required facts and citations (gold KB section IDs),
  - forbidden facts (e.g. a superseded refund window),
  - slice tags (category, difficulty, adversarial, needs-clarification).
- **Incidents**: declarative YAML with a seed. Supported types: `doc_drift` (the policy changes, and a stale copy remains in the index), `api_fault` (timeout, 5xx, 429, malformed payload, expired credential), `prompt_injection` (direct in the ticket, or indirect inside a KB document), `model_swap`, `retrieval_config_change`, `tool_schema_change`, `data_quality` (missing or malformed fields).
- **User simulator**: deterministic. It answers clarifying questions from the case's hidden facts using intent patterns. An LLM-driven user simulator is a later extension that stays off by default.

**Fictional tenants.** Both are clearly labeled fictional in every artifact.

| | **Ledgerloop** (subscription billing SaaS) | **Parcelpoint** (shipping & logistics SaaS) |
|---|---|---|
| Typical tickets | refunds, invoices, plan changes, failed payments, data export | tracking, address change, damage claims, delivery windows |
| Risk tolerance | low (money moves) | medium (latency-sensitive, high volume) |
| Gates | task success lower-bound ≥ 0.85, zero critical violations, approval for refunds > $200 | task success lower-bound ≥ 0.80, p95 latency budget, PII redaction required |
| Escalation | any refund over limit, any account-security request | claims over value threshold, legal/complaint keywords |

### 5.3 `llm` — model access with record and replay

- `LLMClient` protocol: `complete(request) -> response`. The request holds messages, tools, a response schema, and params. The response holds content, tool calls, usage, and latency.
- Providers:
  - `openai_compatible`: any OpenAI-style endpoint (vLLM on Kaggle, llama.cpp server, Ollama, or hosted APIs).
  - `anthropic`: optional extra, for users with keys.
  - `scripted`: deterministic fixtures for unit tests.
  - `heuristic`: a rule-based stand-in agent model with seeded failure modes. It exercises the full pipeline without any GPU. **Every output it produces is watermarked `pipeline-test` and can never feed a reported result.**
- **Cassettes**: content-addressed JSONL records keyed by `sha256(provider, model, canonical request)`. Modes:
  - `record`: call the provider and save the result.
  - `replay`: serve saved results. A cache miss is a hard error.
  - `replay_or_record`
  - `live`
- Replayed responses keep the original latency and token usage, so performance metrics still mean something.
- Tool calling with small open models goes through native tool-call support where the server offers it, with a JSON-schema-constrained fallback.

### 5.4 `retrieval`

- Section-aware chunking that keeps doc ID, section ID, version, and effective dates as metadata.
- BM25 (implemented in-house: small and easy to explain) plus dense embeddings. Embedding models are pluggable:
  - `hashing`: deterministic feature-hashing vectors. Lexical only, needs no download, used in tests and offline runs. It is labeled as a lexical baseline.
  - `sentence_transformers` / `fastembed`: optional extras that use real semantic models, run in-process.
  - Embeddings are cached by content hash.
- Hybrid fusion (reciprocal rank fusion). Optional reranker interface.
- Stores: in-memory/numpy for local runs (the corpus is small), pgvector in Postgres deployments.
- Optional freshness filter (`effective_at <= now`, superseded versions excluded). This is one of the remediations the improvement loop can propose.

### 5.5 `connectors` — integration layer

- A `Connector` protocol: `describe()` (tool schemas), `health()`, `call(op, args, ctx)`.
- `ResilientConnector` wraps any connector with:
  - per-op timeouts,
  - retries with exponential backoff and jitter (retryable errors only),
  - a circuit breaker,
  - a token-bucket rate limit,
  - **idempotency keys** for mutating ops, so a refund cannot happen twice on retry,
  - structured error types the agent can reason about.
- **Permission-aware execution**: every call is checked against the agent's role scopes and the tenant policy before it runs. A denial is a typed error and is logged.
- **Audit log**: append-only and hash-chained (each event holds the previous event's hash), so tampering is detectable.
- **PII redaction** at trace-write time, driven by tenant config.
- **Ingest data-quality report**: when a tenant's business data is loaded, missing or malformed fields are counted, quarantined, and reported. Bad records are never silently dropped.
- Implementations: world connectors (in-process and HTTP), and a generic REST connector with mapping config, tested against a local fake server.

### 5.6 `agent` — reference support agent (system under test)

A small explicit workflow engine (state machine), not a framework:

`intake → classify → retrieve → act (bounded tool loop) → respond | clarify | escalate`

- Prompts are versioned files with content hashes.
- Limits: max tool calls, max tokens, wall-clock budget.
- The agent sees tool errors as structured observations and decides whether to retry, ask, or escalate.
- **External agent adapter**: evaluate any agent exposed as a Python callable or an HTTP endpoint. Its trace can come from OTel GenAI spans or from a returned transcript. This is the main entry point for developers.

### 5.7 `trace` — observability

- The span model follows OpenTelemetry GenAI semantic conventions (`gen_ai.*` attributes) plus our own `fdeops.*` attributes. Span kinds: agent step, LLM call, retrieval, tool call, guard check.
- Each span records inputs, outputs, errors, latency, tokens, and cost.
- Cost model: API price tables for hosted models. Self-hosted models use GPU-seconds × an assumed $/hour, labeled as an estimate.
- Exporters: database (default), JSONL, and optional OTLP.

### 5.8 `eval` — evaluation engine

**Evaluators.** Deterministic first. LLM judges only where judgment is needed.

| Layer | Evaluator | Method |
|---|---|---|
| Task success | `outcome` | world state diff after the episode vs oracle diff (exact match on the decision-relevant fields) |
| Tool use | `tool_calls` | expected/forbidden calls and argument validity |
| Policy | `policy` | re-run the policy engine over the trace's actions |
| Safety | `injection` | forbidden actions not taken, no injected content echoed |
| Escalation | `escalation` | escalated iff the oracle says so (precision/recall reported separately) |
| Retrieval | `retrieval` | recall@k, MRR, nDCG@k against gold section IDs |
| Knowledge | `facts` | required facts present, forbidden (stale) facts absent |
| Groundedness | `judge.groundedness` | LLM judge: claims supported by retrieved evidence |
| Communication | `judge.quality` | LLM judge rubric: clarity, tone, completeness |
| Performance | `perf` | latency p50/p95, tokens, cost per case and per resolution |

**Datasets.**
- Versioned and content-hashed, with provenance (generator version, template, seed, incident).
- Splits: `dev` for diagnosis and tuning, `test` held out for gates. The improvement loop can only read `dev`. Gates only read `test`. Code enforces this.

**Runs.** Cases × *k* trials per configuration. Trials are what make reliability measurable.

**Statistics** (`eval.stats`):
- Wilson intervals for rates.
- Paired bootstrap CIs for metric differences.
- Exact McNemar test for paired pass/fail.
- pass^k: the probability that all k trials succeed.
- Holm correction across slices.
- Rule-of-three upper bound when zero events are observed.
- Power / minimum-detectable-effect calculator to size datasets.

**Judge calibration.** Humans label a sample through the annotation queue (CLI first, then UI). We report Cohen's κ, a confusion matrix, and per-slice agreement. Pairwise judges are run with position swap to measure position bias. A judge with κ below the configured floor cannot gate a release.

### 5.9 `diagnose` — failure analysis

1. **Classify** each failed trial into a fixed taxonomy using deterministic rules over trace + ground truth, with evidence pointers (span IDs):
   `retrieval_miss` · `stale_knowledge` · `grounding_failure` · `wrong_tool` · `bad_arguments` · `permission_violation` · `policy_violation` · `unhandled_tool_error` · `timeout_or_budget` · `injection_followed` · `missed_escalation` · `over_escalation` · `clarification_failure` · `reasoning_error` (residual).
2. **Cluster** failures by taxonomy × slice × incident → failure clusters with counts and affected business volume.
3. **Hypothesize** candidate causes for each cluster from a playbook (e.g. stale knowledge → doc freshness / index version / prompt).
4. **Intervene**: counterfactual replay with one component changed. Options include oracle retrieval (gold sections injected), the previous doc snapshot, the previous prompt, the previous model, a different top-k, or a tool validator. Each intervention reports a fix rate with a CI and a regression rate on passing cases.
5. **Verdict** wording is strict: `confirmed by intervention`, `supported by evidence`, or `inconclusive`.

### 5.10 `improve` — closed improvement loop

Detect → Diagnose → **Recommend** (a remediation as a concrete AgentConfig diff, with expected effect and trade-offs) → **Validate** (experiment on `dev`, then gate run on `test`) → **Release or reject**. Production changes require an `ApprovalRecord` from a user with the `approver` role. Nothing auto-applies.

### 5.11 `release` — releases and gates

- A `Release` is an immutable bundle hash: model + prompt + retrieval config + tools + dataset version + gate config.
- Gates are per tenant YAML. Each gate states its justification:
  - task success: **lower CI bound** ≥ threshold,
  - critical violations: zero observed and rule-of-three upper bound ≤ limit,
  - non-inferiority against the current production release on protected slices (margin δ),
  - p95 latency and cost per resolution within budget,
  - judge calibration κ ≥ floor (if any judge gates),
  - integration tests passed.
- Output: a `ReleaseDecision` record (pass/fail per gate, the evidence, approver, timestamp) and a markdown decision memo.
- Rollback moves the tenant's `production` pointer back to the previous release. Shadow mode runs the candidate on recorded production traffic with no side effects.

### 5.12 `impact` — business impact and ROI

- A per-tenant cost model covers human handling time per category, loaded hourly cost, review cost, cost of a critical error, model/infrastructure cost, and integration/maintenance cost.
- Baselines: human-only, plus a simple non-LLM baseline (retrieval-only FAQ responder) so the LLM agent has to earn its place.
- Outputs: automation rate, escalation rate, cost per successful resolution, net savings and break-even volume, with **Monte Carlo uncertainty over the assumptions**. Each number is labeled measured or assumed.

### 5.13 `insights` — product intelligence

- Combines failure clusters, impact, and experiment results into **opportunities**: the problem, evidence (run/trace links), share of affected cases, severity, cost of the problem, estimated effort (entered by a person), diagnosis confidence, expected benefit (from intervention fix rates × volume × cost), and a validation plan.
- Ranking formula: expected value ÷ effort, weighted by confidence. The formula is shown in the UI and every input can be inspected.
- Generates a roadmap memo that includes a section on what not to build, and why.

### 5.14 `tenancy` — multi-tenant configuration

- Tenant config as code: `tenants/<id>/tenant.yaml` plus a policy file, knowledge docs, dataset specs, a gates file, and a cost model.
- Every DB row has a `tenant_id`. The repository layer enforces a tenant scope, and tests check for cross-tenant leaks.
- Adding a tenant needs only config, no code. Time-to-onboard is measured and reported (an FDE metric).

### 5.15 `storage`, `api`, `jobs`, `cli`

- **Storage**: SQLAlchemy 2.0 + Alembic. SQLite file locally, Postgres in CI and deploys. Large blobs (traces, cassettes, reports) go in an artifact store interface: local filesystem or S3-compatible.
- **API**: FastAPI with OpenAPI docs. API keys are stored hashed and have scopes. Roles: `viewer`, `engineer`, `approver`, `admin`.
- **Jobs**: an in-process runner locally. In deploys, a Postgres-backed queue (`FOR UPDATE SKIP LOCKED`) replaces Celery/Redis, so there is one fewer service to run. The trade-off is recorded in an ADR.
- **CLI**: `fdeops` (Typer). Every capability is usable from the CLI before the UI exists.

### 5.16 `web` — UI

Next.js + TypeScript. Each view answers one decision:

| View | Decision |
|---|---|
| Release review | Ship this candidate or not? |
| Run comparison | Is B better than A, where, and how sure are we? |
| Trace explorer | What exactly happened in this case? |
| Diagnosis | Why does this cluster fail, and which cause is confirmed? |
| Opportunities | What should we build next? |
| ROI | Is this deployment worth it, under which assumptions? |
| Tenant setup | Is this customer configured and healthy? |

A **static demo build** reads exported JSON snapshots, so a public demo needs no backend and no model.

### 5.17 Infrastructure and delivery

- Python ≥ 3.11 managed with `uv`. Tooling: ruff, mypy (strict for `core`, `eval`, `release`), pytest, import-linter.
- Dockerfiles for api, worker, and web. `docker-compose.yml` for the full stack (api, worker, postgres+pgvector, web).
- GitHub Actions:
  - lint/type/test on every push,
  - integration tests against a Postgres service container,
  - an **eval regression job** that replays cassettes and fails the PR if a gate regresses,
  - compose smoke test,
  - docs build.
- **Cloud recording kit**: a Kaggle-ready notebook and script. It starts vLLM with an open 7–8B instruct model, runs `fdeops run --llm-mode record`, and packages cassettes and results for download.
- Deploy configs for at least one free or cheap target, plus the static demo.

## 6. Key flows

### 6.1 Evaluation run
`fdeops run --tenant ledgerloop --config configs/agent/v1.yaml --dataset ledgerloop/test@v3 --trials 3 --llm-mode replay`
→ create Run → for each case and trial: reset the world from its snapshot, run the agent, capture the trace and final world state → evaluators → scores → stats → report (JSON + markdown) labeled with provenance.

### 6.2 The flagship demo story
1. Release `v1` is in production for Ledgerloop.
2. Incident: the refund policy changes from 30 to 14 days (`doc_drift`), and the stale section stays indexed.
3. The monitoring run shows a task-success drop on the `refund` slice. The drop is significant, and the paired test confirms it.
4. Diagnosis clusters the failures as `stale_knowledge`. Interventions: "previous doc snapshot" restores success (which confirms the cause); "freshness filter" fixes 92% of failures with 0 regressions; "bigger model" fixes 40% at 3× cost.
5. Improve proposes `v2` = freshness filter + a reindex job. The experiment runs on `dev`, the gate run on `test`. Gates pass, the approver signs, `v2` is released, and a regression test case is added.
6. ROI and Opportunities update: "retrieval freshness" outranks "model upgrade" on expected value per unit of effort.
7. The postmortem is generated from the actual run records.

(The figures in step 4 are illustrative. Real ones come from recorded runs.)

## 7. Portfolio artifacts (generated from real run data wherever possible)

1. PRD: user, problem, workflow, non-goals, metrics, risks.
2. ADRs: one per significant decision (stack, record/replay, Postgres queue vs Celery, own BM25, gates on lower bounds, etc.).
3. Benchmark report: dataset method, baselines, metrics with CIs, ablations, failure taxonomy, limitations.
4. Incident postmortem (from the demo story).
5. Customer deployment case study: a simulated discovery and onboarding of Parcelpoint, clearly labeled.
6. Roadmap memo: top 3 opportunities, expected impact and cost, dependencies, and what we chose not to build.

## 8. Milestones

Each milestone ends with passing tests and a short "what this proves" note in the changelog.

| # | Milestone | Needs external resources? |
|---|---|---|
| M0 | Repo foundations: tooling, CI config, core models, hashing, config loading | No |
| M1 | Simulated world: KB, data, APIs, policy engine, oracle, case generator, datasets, incidents (spec) | No |
| M2 | LLM layer (protocol, cassettes, scripted/heuristic/openai-compatible), retrieval, connectors + resilience, reference agent, tracing | No |
| M3 | Eval engine: evaluators, runner, statistics, reports | No |
| M4 | Diagnosis: taxonomy, clustering, counterfactual interventions | No |
| M5 | Integration hardening: incidents executable, permissions, audit chain, PII redaction, ingest quality | No |
| M6 | Releases, gates, improvement loop, approvals | No |
| M7 | Storage (SQLite/Postgres), API, jobs, auth, tenancy enforcement | No (Postgres verified in CI) |
| M8 | Impact/ROI and insights/opportunities | No |
| M9 | Web UI + static demo export | No |
| M10 | Docker, Compose, GitHub Actions, Kaggle recording kit, deploy configs | Written locally, executed externally |
| M11 | Real recorded runs, benchmark report, portfolio artifacts with real numbers | **Yes** (Kaggle GPU) |
| M12 | Public deploy and demo, external-agent onboarding guide | **Yes** (GitHub, hosting) |
| — | Start guide outside the repo (how to start, why, what) | Written last |

## 9. Testing strategy

- **Unit**: every evaluator, stat function, policy rule, resilience behavior (fake clock, injected faults), and cassette keying. Statistics are checked against known values (e.g. Wilson, McNemar textbook examples).
- **Property tests** (Hypothesis): the oracle's ground truth matches the policy engine for any generated world. Hashing is stable under key reordering.
- **Integration**: full episode with the `scripted`/`heuristic` model through real connectors and the world. API tests with a test client. Postgres tests in CI only.
- **Golden runs**: a small replay run whose report must not change unless intended (snapshot test).
- **Contract tests** for the external agent adapter.

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Small open models may be too weak for tool use | Model-selection experiment first (M11). The agent design copes with errors. Weak models produce useful failure data. Pluggable providers for stronger ones. |
| The simulation is too clean to be convincing | Incidents, data-quality faults, adversarial templates, and a non-LLM baseline. Limitations sections are explicit. |
| Free GPU quotas | Record once, replay forever. Datasets sized with the power calculator. Batched runs. |
| Scope creep | Milestone gates. Non-goals enforced in reviews. |
| Judge unreliability | Calibration module. Judges cannot gate below the κ floor. Deterministic evaluators carry the gates. |

## 11. Left to the builder

Library choices within the stack (e.g. the specific embedding model, chart library), file-level structure inside each package, exact prompt wording, UI visual design, and the starting gate thresholds. Thresholds must be justified in tenant config comments.

## 12. Decisions made by the author's assistant (flagged for review)

- Domain: B2B SaaS customer support. Tenants Ledgerloop and Parcelpoint (fictional).
- Postgres-backed job queue instead of Celery/Redis.
- In-house BM25 and statistics (with scipy for distributions) for teaching value. Mature libraries elsewhere.
- Gates use CI lower bounds and non-inferiority, not point estimates.
- A `heuristic` model provider exists only to test the pipeline. Its outputs are watermarked and never reported.
- Design docs live in `docs/design/` rather than a tooling-specific folder, so the repo reads well to reviewers.
