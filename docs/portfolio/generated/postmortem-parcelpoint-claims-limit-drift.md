> **Provenance: pipeline-test**. A stand-in model made these numbers. They test the pipeline. They do not measure the quality of an agent.

# Postmortem: `claims-limit-drift` at Parcelpoint (fictional)

*The platform wrote this document from the records of the flagship demo. The tenant and its data are fictional.*

## Summary

The claims limit change is published, but the previous section stays in the index. The support agent v1 used the superseded text, and task success decreased by 12.1 points. The production monitor gave an alert before the evaluation measured the regression. A counterfactual replay confirmed the cause. A fix went through the release gates, and a person approved it.

## Impact

- Task success on the test split changed by -0.121 (95% CI -0.212 to -0.045).
- The largest change was in `damage_claim_large` (-0.571).
- Trials with a critical violation: 8. Each is a wrong money operation or a wrong data operation.
- Estimated cost if the problem continues: about $1,633,133 each month (7,792 tickets each month). This value uses the assumptions in `costs.yaml`.

## Detection

The monitor uses only signals that a live deployment can see. It does not use the oracle. At the likely traffic of 64.9 tickets each hour, these are the alarms:

| signal | severity | reference | during the incident | alarm after | time |
|---|---|---:|---:|---:|---|
| `stale_context` | ticket | 0.0% | 77.3% | 8 ticket(s) | about 7 minutes |
| `critical_flag` | page | 0.0% | 12.1% | 23 ticket(s) | about 21 minutes |
| `policy_flag` | ticket | 0.0% | 12.1% | 23 ticket(s) | about 21 minutes |

The monitor saw 8 of 8 failed trials. 0 failure(s) had no flag.

## Timeline

| step | event | evidence |
|---|---|---|
| 0 | The policy document changes. The index keeps the previous section. | incident `claims-limit-drift` |
| 1 | First alarm: `stale_context` after 8 ticket(s) (about 7 minutes). | run `run_01m697s4988178hjaq07g3z7sn` |
| 2 | The evaluation measures the regression (-0.121). | runs `run_01m697s1mv6mk91sr274vfc79m` and `run_01m697s4988178hjaq07g3z7sn` |
| 3 | Diagnosis: `stale_knowledge:damage_claim_large`, confirmed by intervention. | run `run_01m697s5a9b3zfcg8sm38kqhfn` |
| 4 | The improvement loop proposes `freshness_filter` and stops at `pending_approval`. | proposal `imp_01m697s76ednvhq8fvz5gqxw8e` |
| 5 | A person with the approver role approves v2. | decision `dec_01m697sczydj4h3k4sps7f6bhp` |
| 6 | The monitor gives 0 alert(s) for v2. | run `run_01m697sbhv5vp471r0djbq6pn0` |

## Root cause

**confirmed by intervention.** freshness_filter fixed 8 of 8 cases with 0 regressions in 20 control cases.

Evidence:

- `stale_chunk` `claims#large-claims@v1`: superseded section given to the agent
- `violation` `claim.over_auto_limit`: The claim decision is escalate_over_limit.

| intervention | fixed cases | regressions in control cases |
|---|---:|---:|
| `freshness_filter` | 8 of 8 | 0 of 20 |
| `current_index_only` | 8 of 8 | 0 of 20 |
| `oracle_retrieval` | 8 of 8 | 0 of 20 |

## Resolution

The fix is `freshness_filter`. On the dev split, success changed by +0.167. The test split was used only for the release gates.
Against v1 during the incident, v2 changed success by +0.121 (95% CI +0.045 to +0.212).

v2 passed 8 of 8 gates. The approval added 8 incident cases to the regression suite.

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
