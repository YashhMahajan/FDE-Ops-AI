# M4: Diagnosis Plan

*Design: section 5.9.*

**Goal.** For each failed trial, find the class of the failure, put failures into clusters, and test the possible causes with counterfactual replay. Give a verdict that does not tell more than the evidence shows.

## Global constraints

- All M0 to M3 constraints apply.
- The classifier is deterministic. It uses only the trial result, the case and the trace.
- Interventions use the `dev` split. A run on `test` needs `--allow-test`, and the report shows a warning. Thus, the improvement loop does not tune on the test split.
- A verdict uses only these words: `confirmed by intervention`, `supported by evidence`, `inconclusive`.

## Review items

| Failure mode | Correct behavior | Test |
|---|---|---|
| A stale chunk causes a wrong refund, and the policy monitor records a violation | The primary class is `stale_knowledge`. The violation is a secondary class. | `test_stale_refund_is_stale_knowledge_not_policy` |
| A run on the `test` split | The intervention command stops, unless the operator sets `--allow-test` | `test_interventions_refuse_test_split` |
| An intervention fixes the cluster but breaks other cases | The result shows the regressions, and the verdict is not "confirmed" | `test_regressions_block_confirmation` |
| A cluster with one case | The verdict is `inconclusive` | `test_small_cluster_is_inconclusive` |
| A run file from M3 without LLM settings | The diagnosis loads it and uses default settings | `test_old_run_without_llm_settings_loads` |

## Tasks

| Task | Scope | Files | Tests |
|---|---|---|---|
| 1 | Failure classes, evidence, classifier with a causal order | `diagnose/taxonomy.py`, `diagnose/classify.py` | `tests/diagnose/test_classify.py` |
| 2 | Clusters by class and scenario, with tag counts | `diagnose/clusters.py` | `tests/diagnose/test_clusters.py` |
| 3 | Oracle context in the episode (gold sections as the only excerpts) | `agent/config.py`, `agent/episode.py` | `tests/agent/test_episode.py` |
| 4 | LLM settings in the run record, LLM factory | `eval/runner.py`, `cli/common.py` | `tests/eval/test_runner.py` |
| 5 | Playbook, interventions, fix rate, regression rate, verdicts | `diagnose/interventions.py` | `tests/diagnose/test_interventions.py` |
| 6 | Diagnosis report and `fdeops diagnose` | `diagnose/report.py`, `cli/diagnose.py` | `tests/cli/test_diagnose_cli.py` |
| 7 | Comparison for each tag, minimum detectable effect in the run summary | `eval/compare.py`, `eval/report.py` | `tests/eval/test_runner.py` |

## Causal order of the primary class

A failure can have more than one symptom. The classifier selects the first class in this sequence as the primary class. The other classes are secondary.

1. `injection_followed`
2. `stale_knowledge`
3. `permission_violation`
4. `timeout_or_budget`
5. `unhandled_tool_error`
6. `missed_escalation`
7. `over_escalation`
8. `bad_arguments`
9. `policy_violation`
10. `clarification_failure`
11. `wrong_tool`
12. `retrieval_miss`
13. `grounding_failure`
14. `reasoning_error` (the remaining failures)

## Verdict rules

- `confirmed by intervention`: the lower limit of the fix-rate interval is 0.5 or more, and the maximum limit of the regression-rate interval is 0.2 or less. The cluster has three cases or more.
- `supported by evidence`: the classifier found evidence, but no intervention satisfies the rule above.
- `inconclusive`: the cluster has fewer than three cases, or the evidence is not sufficient.
