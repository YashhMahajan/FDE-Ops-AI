# Changelog

All entries use ASD-STE100. Refer to the [glossary](docs/glossary.md).

## Unreleased

### Documentation

- All documents use ASD-STE100 Simplified Technical English (issue 9).
- `fdeops docs check` finds the STE rules that a program can find: words that are not approved, sentence length, paragraph length, semicolons and contractions. CI runs it.
- The glossary gives the technical nouns and technical verbs of the project.

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
