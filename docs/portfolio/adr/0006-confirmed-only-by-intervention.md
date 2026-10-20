# 0006: A Cause Is Confirmed Only by an Intervention

*Status: accepted.*

## Context

Failures that occur together do not show a cause. For example, superseded text in the context and a wrong refund can occur in the same trials for a different cause. A fix for a cause that is not correct costs time and does not stop the failures.

## Decision

- A deterministic classifier gives each failed trial one class from a taxonomy of 14 classes. A causal sequence selects the class.
- Each pack tells which policy rules each knowledge section controls. Thus, the classifier links a violation to superseded knowledge only when that section controls the rule.
- An intervention runs the failed cases again with one change. It also runs control cases that passed.
- Verdicts: `confirmed by intervention` (a high fix rate and a small number of regressions, with intervals), `supported by evidence`, or `inconclusive`.
- Interventions use the dev split. The test split is only for the release gates.

## Alternatives

- **An LLM that writes the root cause.** Its text sounds correct, but it is not a test.
- **Correlation only.** It gives a hypothesis, not a cause.

## Results

- The diagnosis costs more model calls. Replay makes this cost zero after one recording.
- A diagnostic intervention (for example, oracle retrieval) can show a cause, but it is not a fix that can go to production. The report shows this difference.
