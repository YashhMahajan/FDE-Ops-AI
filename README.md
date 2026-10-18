# FDE-Ops-AI

**Deploy AI agents into real business workflows, then prove with evidence whether they are ready to ship.**

A demo shows an agent answering one question correctly. FDE-Ops-AI answers the questions that come after:

- Does the agent work reliably across many realistic and adversarial cases?
- Does it follow *this customer's* policies and permissions?
- When a document changes or an API fails, can we detect it, find the cause, and prove the fix?
- Is the new release better than the old one, by a margin we can defend statistically?

The first workflow is a customer-support agent for a B2B SaaS company. It looks up accounts, issues refunds, changes plans, and escalates. It runs against a **deterministic simulated customer world** whose ground truth comes from executing the tenant's policy. **No LLM writes the answer key.**

> All companies, people, and data here are **fictional**. Every report states where its numbers come from (`pipeline-test`, `measured-in-simulation`, or `estimated`). Simulated results are never presented as real customer impact.

## What works today (M0–M3)

| Area | What it does |
|---|---|
| Simulated world | Tenant *Ledgerloop* (fictional billing SaaS). Versioned knowledge base with effective dates. Seeded accounts and invoices. Billing, account and ticketing APIs. |
| Ground truth | A policy engine is the oracle. 12 scenario templates cover drift-sensitive refunds, clarification, permission, prompt-injection and unknown-requester cases. |
| Datasets | Content-hashed and versioned, with a dev/test split that is stable by case id. Tampering is detected on load. |
| Agent | Explicit tool loop. Malformed model output becomes an observation, never a crash. Deterministic customer simulator for clarifying questions. |
| Integration layer | Timeouts, retries with backoff, circuit breaker, rate limiting, and **idempotency keys**, so a retried refund happens exactly once. Permission guard, hash-chained audit log, fault injection, and a policy monitor (observe or enforce). |
| Models | One client for the OpenAI-compatible wire format. Free presets: **OpenRouter free models**, vLLM, Ollama. Content-addressed **record/replay cassettes**, so evaluations are reproducible and cost nothing to re-run. |
| Evaluation | Deterministic evaluators (outcome via world-state diff, tool use, policy, escalation, retrieval recall/MRR/nDCG + stale hits, facts, injection, clarification, perf). LLM judges with calibration (Cohen's κ). |
| Statistics | Wilson intervals, pass^k reliability, case-level paired bootstrap, exact sign/McNemar tests, Holm correction, rule-of-three bounds, power/MDE. |

## Quick start

Requires Python ≥ 3.11 and [uv](https://docs.astral.sh/uv/). No GPU, Docker, or API key is needed for this.

```bash
uv sync
make check                                   # lint, types, layering contract, 200+ tests

uv run fdeops tenant validate tenants/ledgerloop
uv run fdeops dataset build --tenant tenants/ledgerloop

# Pipeline test with the rule-based stand-in model: stale index vs. fixed index
uv run fdeops run --tenant tenants/ledgerloop --agent configs/agents/ledgerloop-heuristic-stale.yaml \
  --dataset data/datasets/ledgerloop/support-core@v1 --split test --trials 2
uv run fdeops run --tenant tenants/ledgerloop --agent configs/agents/ledgerloop-heuristic.yaml \
  --dataset data/datasets/ledgerloop/support-core@v1 --split test --trials 2
uv run fdeops compare runs/<stale-run-id> runs/<fixed-run-id>
```

Running a real (free) model through OpenRouter, recording every call:

```bash
export OPENROUTER_API_KEY=...                # free account; pick a model id ending in ":free"
uv run fdeops run --tenant tenants/ledgerloop --agent configs/agents/ledgerloop-v1.yaml \
  --model "<free-model-id>" --dataset data/datasets/ledgerloop/support-core@v1 \
  --llm-mode record --cassettes cassettes/ledgerloop-v1.jsonl
# Later, anywhere, with no key and no cost:
uv run fdeops run ... --llm-mode replay --cassettes cassettes/ledgerloop-v1.jsonl
```

## Layout

```
src/fdeops/
  core/        ids, canonical hashing, clocks, provenance, config errors
  llm/         protocol, OpenAI-compatible client, presets, retries, cassettes
  trace/       spans (OpenTelemetry GenAI attribute names), cost estimates
  retrieval/   versioned knowledge base, BM25, hashing embedder, hybrid retriever
  world/       entity state + diffing, cases, datasets, scenario framework
  connectors/  connector interface, resilience, guard, audit, faults, policy monitor
  packs/       domain packs (billing): entities, APIs, policy, scenarios, heuristic model
  tenancy/     tenant config as code
  agent/       reference support agent, prompts, episode runner
  eval/        evaluators, judges, calibration, runner, reports, comparisons, statistics
  cli/         `fdeops` command
tenants/       one directory per (fictional) customer
configs/       agent configurations (release candidates)
docs/          design, plans, ADRs, reports
```

An import-linter contract enforces the layering in CI. Dependencies point one way only.

## Roadmap

See the [system design](docs/design/2026-10-18-fde-ops-ai-design.md). Next up:
- M4: failure taxonomy, clustering and counterfactual-replay diagnosis.
- M5: integration hardening and a second tenant (Parcelpoint).
- M6: release gates and the improvement loop.
- M7: API, storage and jobs.
- M8: ROI and product insights.
- M9: web UI.
- M10: Docker/CI delivery kit.
- M11–12: real recorded runs and public demo.

## License

MIT
