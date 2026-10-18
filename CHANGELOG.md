# Changelog

## Unreleased

### M3: Evaluation engine
- Deterministic evaluators: outcome (world-state diff against the oracle), tool use, policy, escalation (confusion cells), retrieval (recall/MRR/nDCG, stale hits), facts, injection, clarification, perf.
- LLM judges (groundedness, communication). A failed judgment is "no verdict", never a pass. Calibration against human labels with Cohen's κ and a floor.
- Statistics:
  - Wilson intervals
  - case-level intervals and paired comparisons, because trials of one case are correlated
  - exact sign/McNemar tests
  - Holm correction
  - pass^k
  - rule of three
  - power/MDE
- Runner, markdown reports with a provenance banner, run comparison, and the `fdeops run | report | compare` CLI.
- *What this proves:* a stale-index regression is detected, attributed to the right scenario, and reported with honest uncertainty.

### M2: Agent, models, integration layer
- OpenAI-compatible client with free presets (OpenRouter, vLLM, Ollama), 429 backoff, and record/replay cassettes.
- Tracing, retrieval (BM25, hashing embedder, hybrid RRF, freshness filter).
- Resilient connectors with exactly-once mutating calls, permission guard, audit chain, fault injection, and policy monitor.
- Reference support agent and episode runner. Rule-based stand-in model for pipeline tests.

### M1: Simulated customer world
- Versioned KB, billing domain pack, policy oracle, 12 scenarios, versioned datasets, and the Ledgerloop tenant.

### M0: Foundations
- Tooling, CI config, core primitives.
