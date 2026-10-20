> **Provenance: pipeline-test**. A stand-in model made these numbers. They test the pipeline. They do not measure the quality of an agent.

# Roadmap memo: `ledgerloop`

The values are estimates. They use measured failure rates and the likely value of each assumption. The effort values come from a person.

## What we build next

### 1. The agent used a superseded version of a policy. (refund_outside_window)

- Problem: The agent used a superseded version of a policy. It occurs in 13.7% of trials, about 1,318 tickets each month.
- Severity: critical. Cost of the problem: about $410,227 each month.
- Fix: `freshness_filter`. The fix rate is 65% or more. Verdict: confirmed by intervention.
- Expected benefit: about $264,871 each month for 0.5 engineer weeks (a filter in the retriever and a reindex job).
- Score: 476,768. Confidence: 90%.
- Validation plan: Run the candidate with freshness_filter on the test split. The gates must pass, and the cluster cases must go into the regression suite.
- Evidence: run run_01m5bv1tee6p53cfsn2t0z25xk, cluster stale_knowledge:refund_outside_window: 7 trials, 7 cases, stale_chunk refund-policy#refund-window@v1, violation refund.outside_window.

## What we do not build

- The agent escalated a ticket that it can complete. (refund_outside_window): The evidence is not sufficient. Collect more cases. (cost about $2,133 each month)

## Rank formula

`score = expected_benefit_per_month * confidence / effort_weeks; expected_benefit_per_month = cost_per_month * fix_rate_lower_limit`

The formula prefers fixes that the evidence confirms and that need less effort. A person must examine the effort values, because they are estimates.
