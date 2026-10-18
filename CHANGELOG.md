# Changelog

All entries use ASD-STE100. Refer to the [glossary](docs/glossary.md).

## Unreleased

### Documentation

- All documents use ASD-STE100 Simplified Technical English (issue 9).
- `fdeops docs check` finds the STE rules that a program can find: words that are not approved, sentence length, paragraph length, semicolons and contractions. CI runs it.
- The glossary gives the technical nouns and technical verbs of the project.

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
