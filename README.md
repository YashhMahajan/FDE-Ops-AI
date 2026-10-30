# FDE-Ops-AI

**Deploy AI agents into real business workflows. Find each failure, prove its cause, and release a fix only when cost, latency and risk stay in limits.**

A demo shows that an agent can answer one question correctly. FDE-Ops-AI answers the questions that come after the demo:

- Does the agent do the task correctly in many realistic cases and in adversarial cases?
- Does the agent obey the policies and permissions of this customer?
- When a document changes or an API stops, can we find the problem, find the cause and prove the fix?
- Is the new release better than the current release? Can statistics show that the difference is real?

The first workflow is a customer-support agent for a B2B SaaS company. The agent finds accounts, refunds invoices, changes plans and escalates tickets. It operates in a **deterministic simulated customer world**. The ground truth comes from the policy of the tenant. **An LLM does not write the answers.**

> All companies, persons and data in this repository are **fictional**. Each report shows the source of its numbers: `pipeline-test`, `measured-in-simulation` or `estimated`. We do not show simulated results as real customer results.

## What the platform does

The mission: deploy AI agents into business workflows, evaluate them, find production failures, find the causes, and make the agents better. Cost, latency and risk must stay in the limits of each customer. The [portfolio index](docs/portfolio/README.md) connects each part of the mission to the code and the tests.

| Area | Function |
|---|---|
| Simulated world | Two fictional tenants: *Ledgerloop* (billing SaaS) and *Parcelpoint* (shipping SaaS). Each has a versioned knowledge base with effective dates, business data and APIs. A policy engine is the oracle. |
| Integration layer | Timeouts, retries, a circuit breaker, a rate limit and **idempotency keys**. A permission guard, a policy monitor, an audit log with a hash chain and fault injection. A REST connector from YAML, and an adapter for external agents. |
| Models | One client for the OpenAI-compatible protocol, with free presets: **OpenRouter free models**, vLLM and Ollama. **Cassettes** record each model call. A replay costs nothing. |
| Evaluation | Deterministic evaluators against the oracle, calibrated LLM judges, Wilson intervals, paired comparisons at case level, slices, pass^k and power calculations. |
| Production monitor | Signals that a live deployment can see, **without an oracle**. An alert needs all of the 95% interval to be more than the tolerance. A sequential detector gives the number of tickets before the alarm. |
| Diagnosis | A taxonomy of 14 failure classes, clusters and **counterfactual interventions**. A cause is confirmed only when an intervention fixes it. |
| Releases | Frozen release bundles, gates on confidence limits with an explanation for each gate, an integration suite with faults, shadow mode, approval by a person and rollback. |
| Improvement loop | Selects a fix on the dev split, validates it on the test split, and stops for approval. |
| Business value | ROI as a distribution against a person and against a FAQ baseline. Ranked opportunities and a roadmap memo. |
| Service | FastAPI with API keys and roles, a tenant scope on each request, a job queue in Postgres, Docker and Compose. |
| Web UI | A static Next.js UI: release log, gates, monitor, comparisons, traces, diagnosis, roadmap and business value. |

## Start

You must have Python 3.11 (or a subsequent version) and [uv](https://docs.astral.sh/uv/). You do not need a GPU, Docker or an API key for these steps.

```bash
uv sync
make check                                   # lint, types, layers, docs, tests

# The flagship demo: release, incident, monitor alarm, diagnosis, gated fix, approval, ROI
uv run fdeops demo --tenant tenants/ledgerloop --export web/public/demo
uv run fdeops demo --tenant tenants/parcelpoint --export web/public/demo

# The portfolio documents from the demo records
uv run fdeops portfolio
```

The web UI reads the export. Build it, and open `web/out/index.html` with a static file server:

```bash
cd web && pnpm install && pnpm build
```

## Use it on your own workflow

Make a tenant for your company, and test your own agent against it. You need about 15 minutes for the [quickstart](docs/guides/quickstart.md).

```bash
uv run fdeops doctor                         # check your machine
uv run fdeops init tenants/<your-tenant> --pack billing --name "<Your Company>"
```

Then write the policy and the knowledge base of your company.

Refer to [test your own agent](docs/guides/test-your-own-agent.md) to run your agent in the same tests as the reference agent. The example `careful_refunder.py` reads the policy. On the 51 dev cases of the fictional tenant, it has a success rate of **78.4%** (95% CI 65.4% to 87.5%) and **0** critical violations. The example `naive_refunder.py` does not read the policy. It has **21.6%** (95% CI 12.5% to 34.6%) and **33** trials with a critical violation. The paired difference is +56.9 points (95% CI +43.1 to +70.6), and the careful agent is better in 29 cases and worse in 0 cases.

These are the commands for each step of the workflow:

| Step | Command |
|---|---|
| Set up | `fdeops doctor`, `fdeops init`, `fdeops tenant validate`, `fdeops dataset build` |
| Evaluate | `fdeops run`, `fdeops compare` |
| Monitor production | `fdeops monitor REFERENCE_RUN CURRENT_RUN --tenant tenants/ledgerloop` |
| Find the cause | `fdeops diagnose RUN --tenant ... --dataset ...` |
| Fix and release | `fdeops improve`, `fdeops release propose`, `fdeops release approve`, `fdeops release rollback` |
| Business value | `fdeops impact`, `fdeops opportunities` |
| Regression in CI | `fdeops regress evals/regression.yaml` |
| Service | `fdeops serve`, `fdeops worker`, `fdeops keys create` |

Real model runs are free with OpenRouter free models or with vLLM on a free Kaggle GPU. Refer to [real model runs](docs/guides/real-model-runs.md).

To deploy the service, use `docker compose up -d --build` on a server, or the Render blueprint in `render.yaml`. CI starts the full Compose stack and runs a job through it.

## Production readiness

| Area | Where |
|---|---|
| Operations: deploy, roll back, backups, keys, incidents, service levels | [runbook](docs/operations/runbook.md) |
| All settings | [configuration reference](docs/operations/configuration.md) and `.env.example` |
| Threats, controls and the risks that stay | [threat model](docs/operations/threat-model.md) |
| Data, PII, model providers, retention and deletion | [data and privacy](docs/operations/data-and-privacy.md) |
| How to report a vulnerability | [security policy](SECURITY.md) |
| How to change the code | [contributing](CONTRIBUTING.md) |

CI examines each change with these checks:

- lint with security rules, types and the layer contract,
- tests on Python 3.11 and 3.12 with a minimum coverage, and the same storage tests on Postgres,
- the Docker stack, and the web build with accessibility checks,
- dependency audits, license checks and a secret check of the git history,
- a check that each command in the documents runs.

## Layout

```
src/fdeops/
  core/        IDs, canonical hashes, clocks, provenance, configuration errors
  llm/         protocol, OpenAI-compatible client, presets, retries, cassettes
  trace/       spans (OpenTelemetry GenAI attribute names), cost estimates
  retrieval/   versioned knowledge base, BM25, hashing embedder, hybrid retriever
  world/       entity state and diffs, cases, datasets, scenario framework
  connectors/  connector interface, resilience, guard, audit, faults, policy monitor
  packs/       domain packs (billing, logistics): entities, APIs, policy, scenarios, rule-based model
  tenancy/     tenant configuration as code
  agent/       reference support agent, prompts, episode runner
  eval/        evaluators, judges, calibration, runner, reports, comparisons, statistics
  monitor/     production monitor without an oracle: signals, detection, reports
  diagnose/    failure taxonomy, clusters, counterfactual interventions
  release/     release bundles, gates, integration suite, registry, shadow mode, memos
  improve/     the improvement loop
  impact/      costs, measured outcomes, FAQ baseline, ROI
  insights/    opportunities and the roadmap memo
  storage/     database, artifact store, tenant-scoped repository, API keys
  jobs/        job queue in the database and the worker
  api/         FastAPI service
  demo/        the flagship demo, the web export and the portfolio documents
  devtools/    the text checker for documents
  templates/   starter tenant files that `fdeops init` copies
  cli/         the `fdeops` command
tenants/       one folder for each fictional customer (policy, KB, gates, monitors, costs)
incidents/     incidents as YAML files, for each tenant
configs/       agent configurations (release candidates)
evals/         the regression manifest and the cassettes
web/           the Next.js UI
docker/        images for the API, the worker and the web UI
kaggle/        the notebook that records real model runs on a free GPU
docs/          design, plans, guides, glossary and the portfolio documents
```

An import-linter contract makes sure that each layer imports only from the layers below it. CI runs this contract.

## Status

Version 2.2 has milestones 0 to 10, and the kit to use the platform on your own workflow. Refer to the [release notes](https://github.com/YashhMahajan/FDE-Ops-AI/releases) and the [system design](docs/design/2026-10-18-fde-ops-ai-design.md).

| Milestone | Scope | Needs |
|---|---|---|
| Milestone 11 | Real recorded runs and a benchmark with real numbers | A free OpenRouter key or a free Kaggle GPU |
| Milestone 12 | A public demo | A decision by the owner of the repository |

## License

MIT
