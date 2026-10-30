# Milestones 0 to 3: Work Record

*Status: complete.*

**Goal.** Make a Python library and a CLI that do these tasks without a network, a GPU or a service:

1. Generate a deterministic simulated world for the fictional tenant Ledgerloop.
2. Make versioned datasets. A policy oracle calculates their ground truth.
3. Run a reference support agent on the datasets. The agent can use a scripted model, a heuristic model or a real model through cassettes.
4. Evaluate the results with confidence intervals.

**Design.** Refer to [the system design](../design/2026-10-18-fde-ops-ai-design.md).

## Global constraints

- Python 3.11 or a subsequent version. Local development uses Python 3.12 from uv.
- Tests do not use the network, a GPU, Docker or a service. HTTP tests use `httpx.MockTransport`.
- The same seed and the same specification give the same dataset hash.
- Money is an integer number of cents. Times have a time zone (UTC).
- Each run report shows its provenance. A run with the heuristic model or the scripted model has the label `pipeline-test`.
- Each tenant must have `fictional: true` in its `tenant.yaml`.
- Domain models are frozen and do not accept unknown fields (`FrozenModel`).

## Review items

The plan identified these five failure modes. Each failure mode has a test.

| Failure mode | Correct behavior | Test |
|---|---|---|
| A retry after a timeout of a refund that succeeded | The refund occurs only one time | `test_timeout_after_success_retry_does_not_double_refund` |
| A cassette miss in replay mode | `CassetteMiss` occurs. The live provider gets no call. | `test_replay_miss_raises_and_never_calls_inner` |
| A tool call that is not correct (unknown tool, bad JSON, bad types) | The model gets an `INVALID_ARGUMENT` message. The episode continues. | `test_malformed_tool_call_is_observation_not_crash` |
| A ticket from an unknown email address | The correct result is a reply that tells the requester to use the email address of the account. The agent does not stop. | `test_unknown_requester_expects_clarification` |
| A KB document that is not correct (no frontmatter, two equal anchors) | A `ConfigError` names the file | `test_duplicate_anchor_error_names_file` |

## Tasks

| Task | Scope | Main files | Tests |
|---|---|---|---|
| 1 | Repository, tools, CI configuration | `pyproject.toml`, `Makefile`, `.github/workflows/ci.yml` | `tests/test_smoke.py` |
| 2 | Core primitives: IDs, canonical JSON, hashes, clocks, provenance, configuration errors | `src/fdeops/core/` | `tests/core/` |
| 3 | World state and diffs | `world/state.py` | `tests/world/test_state.py` |
| 4 | Versioned knowledge base | `retrieval/kb.py` | `tests/retrieval/test_kb.py` |
| 5 | Cases, ground truth, scenario framework, datasets | `world/cases.py`, `world/dataset.py` | `tests/world/test_dataset.py` |
| 6 | Connector interface | `connectors/base.py` | `tests/connectors/test_base.py` |
| 7 | Billing entities, state and base world | `packs/billing/entities.py`, `generator.py` | `test_generator.py` |
| 8 | Billing, account and ticket APIs | `packs/billing/ops.py` | `test_ops.py` |
| 9 | Billing policy engine | `packs/billing/policy.py` | `test_policy.py` |
| 10 | Twelve scenarios, user simulator, oracle | `packs/billing/scenarios.py` | `test_scenarios.py` (with a property test) |
| 11 | Ledgerloop tenant, tenant loader, `fdeops dataset build` | `tenants/ledgerloop/`, `tenancy/` | `tests/tenancy/`, `tests/cli/` |
| 12 | LLM types, cassettes, recording client, scripted model | `llm/` | `tests/llm/test_cassette.py` |
| 13 | OpenAI-compatible client, free presets, retries | `llm/openai_compat.py`, `presets.py`, `retrying.py` | `tests/llm/` |
| 14 | Traces and cost estimates | `trace/` | `tests/trace/` |
| 15 | BM25, hashing embedder, hybrid retriever | `retrieval/` | `tests/retrieval/test_retriever.py` |
| 16 | Resilience, guard, faults, audit chain, policy monitor | `connectors/` | `tests/connectors/` |
| 17 | Support agent and episode runner | `agent/` | `tests/agent/` |
| 18 | Heuristic model and an end-to-end test | `packs/billing/heuristic.py` | `test_heuristic_e2e.py` |
| 19 | Statistics | `eval/stats.py` | `tests/eval/test_stats.py` |
| 20 | Deterministic evaluators | `eval/evaluators.py` | `tests/eval/test_evaluators.py` |
| 21 | LLM judges and calibration | `eval/judges.py`, `eval/calibration.py` | `tests/eval/test_judges.py` |
| 22 | Runner, reports, comparison, CLI | `eval/runner.py`, `report.py`, `compare.py`, `cli/run.py` | `tests/eval/test_runner.py`, golden summary |

## Decisions during the work

Each decision has the cost if the decision is not correct.

| Task | Decision | Cost if not correct |
|---|---|---|
| All | Local commits for each milestone. A push only after the author approves. | No cost |
| 9 | The policy check uses only what a production guardrail can see (state and requester). The tool-use evaluator grades security requests. | Security failures show as tool-use failures |
| 10, 11 | The `world` layer is above `retrieval`, because datasets use the versioned KB. | Move the KB into `world` |
| 12, 13 | OpenRouter, vLLM and Ollama presets. No paid provider. | No cost |
| 15 | `trace.cost` uses token counts, not `llm.Usage`, because the two packages are in the same layer. | No cost |
| 16 | A policy monitor in the connector chain checks the state before each task. It has an enforce mode. | No cost |
| 18 | The heuristic model came before its test. Its tests use the `heuristic_model` function of the pack. | Some branches of a test-only module have no test |
| 22 | Slice intervals use the number of cases when a run has more than one trial. | The intervals are wider than necessary |
| 22 | Comparisons pair at case level and use an exact sign test. Pairs at trial level gave too much confidence. | Less power with many random trials |
| 22 | `refund_outside_window` has 40 cases. The test split has seven drift cases. That is not sufficient for a slice result after the Holm correction. The report tells this. | Milestone 4 adds comparisons for each tag and a dataset-size calculation |

## Last review

The author of the code did the last review. No other reviewer did a review. The review found two problems, and the author fixed them:

1. A judge failure kept `NaN` in `Score.value`. The run file did not load again. At this time, the value is `None`. Test: `test_failed_judgment_survives_run_roundtrip`.
2. The episode found a business task from the name of the operation. At this time, it uses `OpSpec.terminal`.

These small items are for a subsequent milestone:

- The drift slice is small in each split.
- The heuristic model has branches without a test.
- `run.json` keeps full traces. Milestone 7 moves traces to the artifact store.
