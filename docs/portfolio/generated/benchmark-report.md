> **Provenance: pipeline-test**. A stand-in model made these numbers. They test the pipeline. They do not measure the quality of an agent.

# Benchmark Report

*Language: ASD-STE100. The platform wrote this document from the records of the flagship demo for each tenant.*

## Setup

| tenant | dataset | test cases | dev cases | model | trials |
|---|---|---:|---:|---|---:|
| Ledgerloop (fictional) | `ledgerloop/support-core@v1/test` | 69 | 51 | `heuristic` | 1 |
| Parcelpoint (fictional) | `parcelpoint/support-core@v1/test` | 66 | 48 | `heuristic` | 1 |

Each interval is a 95% interval. With more than one trial for each case, the interval uses the number of cases as the sample size.

## Task success

| tenant | run | success | 95% CI | critical trials | p95 latency (ms) | tokens |
|---|---|---:|---|---:|---:|---:|
| ledgerloop | v1 before the incident | 100.0% | 94.7% to 100.0% | 0 | 2,067 | 3,266 |
| ledgerloop | v1 during the incident | 89.9% | 80.5% to 95.0% | 7 | 2,303 | 3,481 |
| ledgerloop | v2 with the fix | 100.0% | 94.7% to 100.0% | 0 | 2,067 | 3,285 |
| ledgerloop | FAQ baseline, no LLM | 47.8% | 36.5% to 59.4% | 0 | 1 | 0 |
| parcelpoint | v1 before the incident | 100.0% | 94.5% to 100.0% | 0 | 2,028 | 2,742 |
| parcelpoint | v1 during the incident | 87.9% | 77.9% to 93.7% | 8 | 2,028 | 3,166 |
| parcelpoint | v2 with the fix | 100.0% | 94.5% to 100.0% | 0 | 2,028 | 2,833 |
| parcelpoint | FAQ baseline, no LLM | 18.2% | 10.7% to 29.1% | 0 | 1 | 0 |

## Paired comparisons

| tenant | comparison | change | 95% CI | p (sign test) |
|---|---|---:|---|---:|
| ledgerloop | v1, then the incident | -0.101 | -0.174 to -0.043 | 0.0156 |
| ledgerloop | the incident, then v2 | +0.101 | +0.043 to +0.174 | 0.0156 |
| parcelpoint | v1, then the incident | -0.121 | -0.212 to -0.045 | 0.0078 |
| parcelpoint | the incident, then v2 | +0.121 | +0.045 to +0.212 | 0.0078 |

## Release gates

| tenant | release | gates passed | status |
|---|---|---:|---|
| ledgerloop | v1 | 8 of 8 | approved |
| ledgerloop | v2 | 8 of 8 | approved |
| parcelpoint | v1 | 8 of 8 | approved |
| parcelpoint | v2 | 8 of 8 | approved |

## Production monitor

| tenant | window | alerts | first alarm | failures seen | silent failures |
|---|---|---:|---|---:|---:|
| ledgerloop | during incident | 3 | `stale_context` after 1 tickets | 7 of 7 | 0 |
| ledgerloop | after fix | 0 | none | 0 of 0 | 0 |
| parcelpoint | during incident | 3 | `stale_context` after 8 tickets | 8 of 8 | 0 |
| parcelpoint | after fix | 0 | none | 0 of 0 | 0 |

## Limits

- The world is a simulation with a deterministic oracle. It is not customer traffic.
- With the stand-in model, the numbers test the platform. They do not measure an agent.
- A real model run replaces these numbers. Refer to `docs/guides/real-model-runs.md`.

## How to get the same numbers

```bash
uv run fdeops portfolio --out docs/portfolio/generated
```

The run IDs change at each run. The numbers do not change, because each run has a seed.
