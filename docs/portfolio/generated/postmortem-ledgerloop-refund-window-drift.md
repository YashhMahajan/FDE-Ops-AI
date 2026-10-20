> **Provenance: pipeline-test**. A stand-in model made these numbers. They test the pipeline. They do not measure the quality of an agent.

# Postmortem: `refund-window-drift` at Ledgerloop (fictional)

*Language: ASD-STE100. The platform wrote this document from the records of the flagship demo. The tenant and its data are fictional.*

## Summary

The refund-policy change is published, but the previous section stays in the index. The support agent v1 used the superseded text, and task success decreased by 10.1 points. The production monitor gave an alert before the evaluation measured the regression. A counterfactual replay confirmed the cause. A fix went through the release gates, and a person approved it.

## Impact

- Task success on the test split changed by -0.101 (95% CI -0.174 to -0.043).
- The largest change was in `refund_outside_window` (-0.350).
- Trials with a critical violation: 7. Each is a wrong money operation or a wrong data operation.
- Estimated cost if the problem continues: about $410,227 each month (1,318 tickets each month). This value uses the assumptions in `costs.yaml`.

## Detection

The monitor uses only signals that a live deployment can see. It does not use the oracle. At the likely traffic of 13.3 tickets each hour, these are the alarms:

| signal | severity | reference | during the incident | alarm after | time |
|---|---|---:|---:|---:|---|
| `stale_context` | ticket | 0.0% | 85.5% | 1 ticket(s) | about 4 minutes |
| `policy_flag` | page | 0.0% | 10.1% | 48 ticket(s) | about 3.6 hours |
| `critical_flag` | page | 0.0% | 10.1% | 50 ticket(s) | about 3.8 hours |

The monitor saw 7 of 7 failed trials. 0 failure(s) had no flag.

## Timeline

| step | event | evidence |
|---|---|---|
| 0 | The policy document changes. The index keeps the previous section. | incident `refund-window-drift` |
| 1 | First alarm: `stale_context` after 1 ticket(s) (about 4 minutes). | run `run_01m5by54194d9tf81jdeeyvdtq` |
| 2 | The evaluation measures the regression (-0.101). | runs `run_01m5by53678fc825y3x2bvb2nc` and `run_01m5by54194d9tf81jdeeyvdtq` |
| 3 | Diagnosis: `stale_knowledge:refund_outside_window`, confirmed by intervention. | run `run_01m5by54cp6694zs5srsqx8esg` |
| 4 | The improvement loop proposes `freshness_filter` and stops at `pending_approval`. | proposal `imp_01m5by54zacestyh78jk74wehf` |
| 5 | A person with the approver role approves v2. | decision `dec_01m5by56sfd6ynaa8xbz3sxw1h` |
| 6 | The monitor gives 0 alert(s) for v2. | run `run_01m5by56cheddqfy38tk5va7fr` |

## Root cause

**confirmed by intervention.** freshness_filter fixed 7 of 7 cases with 0 regressions in 20 control cases.

Evidence:

- `stale_chunk` `refund-policy#refund-window@v1`: superseded section given to the agent
- `violation` `refund.outside_window`: The customer paid the invoice 30 days ago. The refund window is 14 days.

| intervention | fixed cases | regressions in control cases |
|---|---:|---:|
| `freshness_filter` | 7 of 7 | 0 of 20 |
| `current_index_only` | 7 of 7 | 0 of 20 |
| `oracle_retrieval` | 7 of 7 | 0 of 20 |

## Resolution

The fix is `freshness_filter`. On the dev split, success changed by +0.137. The test split was used only for the release gates.
Against v1 during the incident, v2 changed success by +0.101 (95% CI +0.043 to +0.174).

v2 passed 8 of 8 gates. The approval added 7 incident cases to the regression suite.

## What occurred correctly

- The monitor found the drift from the context of the agent, before the critical flags.
- The diagnosis tested the cause with an intervention. It did not use a correlation only.
- The improvement loop stopped before production. A person made the release decision.

## What we must make better

- The release gates of v1 did not examine the index for superseded sections.
- The policy guardrail was in `observe` mode. Thus, wrong operations occurred before the fix.

## Tasks

| task | owner | evidence |
|---|---|---|
| Add the incident cases to the regression suite | release owner | the approval of v2 |
| Add a check of the index for superseded sections to the release gates | platform team | the root cause |
| Set the policy guardrail to enforce mode for critical rules | tenant owner | the critical flags |
