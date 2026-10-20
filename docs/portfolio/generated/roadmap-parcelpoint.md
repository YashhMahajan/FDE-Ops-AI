> **Provenance: pipeline-test**. A stand-in model made these numbers. They test the pipeline. They do not measure the quality of an agent.

# Roadmap memo: `parcelpoint`

The values are estimates. They use measured failure rates and the likely value of each assumption. The effort values come from a person.

## What we build next

### 1. The agent used a superseded version of a policy. (damage_claim_large)

- Problem: The agent used a superseded version of a policy. It occurs in 16.7% of trials, about 7,792 tickets each month.
- Severity: critical. Cost of the problem: about $1,633,133 each month.
- Fix: `freshness_filter`. The fix rate is 68% or more. Verdict: confirmed by intervention.
- Expected benefit: about $1,103,333 each month for 0.5 engineer weeks (a filter in the retriever and a reindex job).
- Score: 1,985,999. Confidence: 90%.
- Validation plan: Run the candidate with freshness_filter on the test split. The gates must pass, and the cluster cases must go into the regression suite.
- Evidence: run run_01m5bt25010kx6pr4x0qh2g2hv, cluster stale_knowledge:damage_claim_large: 8 trials, 8 cases, stale_chunk claims#large-claims@v1, violation claim.over_auto_limit, stale_chunk claims#large-claims@v1.

## What we do not build

Each opportunity has a validated fix.


## Rank formula

`score = expected_benefit_per_month * confidence / effort_weeks; expected_benefit_per_month = cost_per_month * fix_rate_lower_limit`

The formula prefers fixes that the evidence confirms and that need less effort. A person must examine the effort values, because they are estimates.
