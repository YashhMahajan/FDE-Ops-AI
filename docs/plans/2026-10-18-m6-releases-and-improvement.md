# M6: Releases, Gates and the Improvement Loop

*Language: ASD-STE100. Refer to the [glossary](../glossary.md). Design: sections 5.10 and 5.11.*

**Goal.** Make each release a frozen bundle with evidence. A candidate goes to production only when it passes the gates of its tenant and a person with the approver role approves it. The improvement loop finds a fix on the dev split, validates it on the test split, and stops before production.

## Global constraints

- All M0 to M5 constraints apply.
- A gate uses a confidence limit, not a point estimate.
- A gate that the platform cannot measure fails, unless the tenant configuration lets it pass and explains why.
- The improvement loop reads the dev split only. The gate run uses the test split only.
- No code path moves the production pointer without an approval record.
- Each decision keeps its evidence: the run IDs, each gate result and the approver.

## Tasks

| Task | Scope | Files | Tests |
|---|---|---|---|
| 1 | Release bundle, gate configuration with an explanation for each gate | `release/models.py`, `tenants/*/gates.yaml` | `tests/release/test_models.py` |
| 2 | Gate evaluation: success, critical violations, non-inferiority for each slice, latency, cost, judge κ, integration suite, regression suite | `release/gates.py` | `tests/release/test_gates.py` |
| 3 | Integration suite: fault incidents on a sample, no crash, no task two times, a correct audit chain | `release/integration.py` | `tests/release/test_integration.py` |
| 4 | Release registry on disk: propose, approve, reject, rollback, history | `release/registry.py` | `tests/release/test_registry.py` |
| 5 | Shadow mode: the candidate and production on the same traffic, without gates | `release/shadow.py` | `tests/release/test_shadow.py` |
| 6 | Improvement loop: diagnosis, candidate, dev experiment, test gate run, decision that waits for approval | `improve/loop.py` | `tests/improve/test_loop.py` |
| 7 | Decision memo and CLI: `fdeops release`, `fdeops improve` | `release/memo.py`, `cli/release.py` | `tests/cli/test_release_cli.py` |

## Review items

| Failure mode | Correct behavior | Test |
|---|---|---|
| A gate run on the dev split | The gates stop with an error | `test_gates_refuse_dev_split` |
| A candidate that is better in total but worse on an important slice | The non-inferiority gate fails | `test_slice_regression_fails_non_inferiority` |
| An approval from a user without the approver role | The registry refuses it and production does not change | `test_approval_needs_approver_role` |
| A rollback when there is no previous release | A clear error, and production does not change | `test_rollback_without_history_fails` |
| A cost gate when the model has no price | The gate fails as "not measured" unless the configuration accepts it | `test_unmeasured_gate_fails_by_default` |
