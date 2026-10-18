# FDE-Ops-AI

**Deploy AI agents into business workflows. Then, prove with evidence that they can go to production.**

A demo shows that an agent can answer one question correctly. FDE-Ops-AI answers the questions that come after the demo:

- Does the agent do the task correctly in many realistic cases and in adversarial cases?
- Does the agent obey the policies and permissions of this customer?
- When a document changes or an API stops, can we find the problem, find the cause and prove the fix?
- Is the new release better than the current release? Can statistics show that the difference is real?

The first workflow is a customer-support agent for a B2B SaaS company. The agent finds accounts, refunds invoices, changes plans and escalates tickets. It operates in a **deterministic simulated customer world**. The ground truth comes from the policy of the tenant. **An LLM does not write the answers.**

> All companies, persons and data in this repository are **fictional**. Each report shows the source of its numbers: `pipeline-test`, `measured-in-simulation` or `estimated`. We do not show simulated results as real customer results.

## What operates at this time (M0 to M3)

| Area | Function |
|---|---|
| Simulated world | The tenant *Ledgerloop* is a fictional billing SaaS company. It has a versioned knowledge base with an effective date for each document, accounts, invoices, and billing, account and ticket APIs. |
| Ground truth | A policy engine is the oracle. Twelve scenario templates make cases for refunds, clarification, permissions, prompt injection and unknown requesters. |
| Datasets | Each dataset has a version and a content hash. The dev split and the test split do not change when you add cases. The loader finds changes to a dataset file. |
| Agent | The agent is an explicit tool loop. Incorrect model output goes back to the model as an error message. It does not stop the program. |
| Integration layer | Timeouts, retries, a circuit breaker, a rate limit and **idempotency keys**. A refund that the connector sends again occurs only one time. There is also a permission guard, an audit log with a hash chain, fault injection and a policy monitor. |
| Models | One client for the OpenAI-compatible protocol. The presets are free: **OpenRouter free models**, vLLM and Ollama. **Cassettes** record each model call. A replay of a cassette gives the same results and costs nothing. |
| Evaluation | Deterministic evaluators measure the outcome, tool use, policy, escalation, retrieval, facts, injection, clarification and performance. LLM judges have a calibration with human labels. |
| Statistics | Wilson intervals, pass^k reliability, paired comparisons at case level, exact sign tests, Holm correction, the rule of three and power calculations. |

## Start

You must have Python 3.11 (or a subsequent version) and [uv](https://docs.astral.sh/uv/). You do not need a GPU, Docker or an API key for these steps.

```bash
uv sync
make check                                   # lint, types, layers, STE docs, tests

uv run fdeops tenant validate tenants/ledgerloop
uv run fdeops dataset build --tenant tenants/ledgerloop

# A pipeline test with the rule-based model: a stale index, then a correct index
uv run fdeops run --tenant tenants/ledgerloop --agent configs/agents/ledgerloop-heuristic-stale.yaml \
  --dataset data/datasets/ledgerloop/support-core@v1 --split test --trials 2
uv run fdeops run --tenant tenants/ledgerloop --agent configs/agents/ledgerloop-heuristic.yaml \
  --dataset data/datasets/ledgerloop/support-core@v1 --split test --trials 2
uv run fdeops compare runs/<stale-run-id> runs/<correct-run-id>
```

To use a real model that is free, do these steps:

1. Get a free OpenRouter key. Select a model ID that ends with `:free`.
2. Run the agent in record mode. The cassette keeps each model response.
3. Run the agent again in replay mode. You do not need a key for replay.

```bash
export OPENROUTER_API_KEY=...
uv run fdeops run --tenant tenants/ledgerloop --agent configs/agents/ledgerloop-v1.yaml \
  --model "<free-model-id>" --dataset data/datasets/ledgerloop/support-core@v1 \
  --llm-mode record --cassettes cassettes/ledgerloop-v1.jsonl
uv run fdeops run ... --llm-mode replay --cassettes cassettes/ledgerloop-v1.jsonl
```

## Layout

```
src/fdeops/
  core/        IDs, canonical hashes, clocks, provenance, configuration errors
  llm/         protocol, OpenAI-compatible client, presets, retries, cassettes
  trace/       spans (OpenTelemetry GenAI attribute names), cost estimates
  retrieval/   versioned knowledge base, BM25, hashing embedder, hybrid retriever
  world/       entity state and diffs, cases, datasets, scenario framework
  connectors/  connector interface, resilience, guard, audit, faults, policy monitor
  packs/       domain packs (billing): entities, APIs, policy, scenarios, rule-based model
  tenancy/     tenant configuration as code
  agent/       reference support agent, prompts, episode runner
  eval/        evaluators, judges, calibration, runner, reports, comparisons, statistics
  devtools/    the ASD-STE100 checker for documents
  cli/         the `fdeops` command
tenants/       one folder for each fictional customer
configs/       agent configurations (release candidates)
docs/          design, plans, glossary, decision records, reports
```

An import-linter contract makes sure that each layer imports only from the layers below it. CI runs this contract.

## Documentation style

All documents use ASD-STE100 Simplified Technical English. The [glossary](docs/glossary.md) gives the technical nouns and technical verbs of this project. Run `uv run fdeops docs check README.md docs` to check a document.

## Roadmap

Refer to the [system design](docs/design/2026-10-18-fde-ops-ai-design.md). These are the subsequent milestones:

| Milestone | Scope |
|---|---|
| M4 | Failure classes, clusters and diagnosis with counterfactual replay |
| M5 | More resilient integrations and a second tenant (Parcelpoint) |
| M6 | Release gates and the improvement loop |
| M7 | API, storage and jobs |
| M8 | ROI and product insights |
| M9 | Web UI |
| M10 | Deployment kit: Docker, CI, Kaggle notebook |
| M11 and M12 | Real recorded runs and a public demo |

## License

MIT
