# M0–M3: Foundations → Simulated World → Agent → Evaluation Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A tested Python library and CLI that does four things end to end, with no network, GPU, or running services:
- generates a deterministic simulated customer world for the fictional tenant *Ledgerloop*,
- builds versioned datasets whose ground truth comes from a policy oracle,
- runs a reference support agent against them (scripted or heuristic models, with record/replay cassettes),
- evaluates the results with confidence intervals.

**Architecture:** Synchronous, layered package `fdeops` with a one-way dependency rule:
`core → (llm, trace, retrieval, world) → connectors → packs → tenancy → agent → eval → cli`.
The generic world engine stays separate from domain packs (`packs/billing`). Ground truth is computed, never written by an LLM.

**Tech Stack:** Python ≥3.11, uv, Pydantic v2, PyYAML, jsonschema, numpy, scipy, httpx, Typer. Dev tools: pytest, hypothesis, ruff, mypy, import-linter.

**Spec:** `docs/design/2026-10-18-fde-ops-ai-design.md`

## Global Constraints

- `requires-python = ">=3.11"`. Local development uses uv-managed Python 3.12.
- No test touches the network, a GPU, Docker, or a running service. HTTP is tested with `httpx.MockTransport`.
- Everything is deterministic from seeds. The same seed and spec produce the same dataset `content_hash`.
- Money is `int` cents and never `float`. Datetimes are timezone-aware UTC. Dates used for policy are `datetime.date`.
- Every run report shows its provenance (`measured-in-simulation` | `estimated` | `pipeline-test`). Runs that use the `heuristic` or `scripted` model are always `pipeline-test`.
- Tenants are fictional, and `tenant.yaml` must set `fictional: true`.
- Pydantic domain models are frozen with `extra="forbid"` (via `fdeops.core.model.FrozenModel`). Runtime-mutable state (`WorldState`, `Span`) is the only exception.
- Never read, copy from, or modify `~/Desktop/Projects/TrustBench-LLM-Eval`.

## Review Focus

1. **A retry after a timed-out mutating call** (the refund succeeded but the response was lost) must not refund twice. Pinned in Task 16 (`test_timeout_after_success_retry_does_not_double_refund`).
2. **A cassette miss in replay mode** must raise `CassetteMiss` and must never call a live provider. Pinned in Task 12 (`test_replay_miss_raises_and_never_calls_inner`).
3. **Malformed model tool calls** (unknown tool, missing or wrong-typed args, non-JSON arguments) come back to the model as structured `INVALID_ARGUMENT` observations, and the episode keeps going. Pinned in Task 17 (`test_malformed_tool_call_is_observation_not_crash`).
4. **A ticket from an unknown email or one with no identifiers** gets an oracle expectation of clarification or escalation, and the agent path does not crash. Pinned in Task 10 (`test_unknown_requester_expects_clarification`) and Task 17.
5. **A malformed KB document** (missing frontmatter, duplicate anchors, overlapping versions) fails with a `ConfigError` that names the file. Pinned in Task 4 (`test_duplicate_anchor_error_names_file`).

---

## Milestone M0 — Foundations

### Task 1: Repository scaffold and tooling

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.python-version`, `README.md`, `LICENSE` (MIT), `CHANGELOG.md`, `Makefile`, `.github/workflows/ci.yml`, `src/fdeops/__init__.py`, `src/fdeops/py.typed`
- Test: `tests/test_smoke.py`

**Interfaces:** Produces `fdeops.__version__ == "0.1.0"`, plus a `make check` target that runs ruff, mypy, lint-imports, and pytest.

- [ ] Write `test_package_imports_and_has_version`. It asserts `fdeops.__version__ == "0.1.0"`.
- [ ] Run `uv run pytest tests/test_smoke.py -v`. Expected: FAIL (no package).
- [ ] Create the files. The `pyproject.toml` defines:
  - a hatchling src layout,
  - an `fdeops` console script pointing to `fdeops.cli.main:app`,
  - ruff config (line length 100; select E,F,I,B,UP,SIM,RUF),
  - mypy (strict on `fdeops.core`, `fdeops.eval`),
  - import-linter `layers` contract matching the Architecture line.
- [ ] Run `uv sync && uv run pytest -q`. Expected: PASS.
- [ ] CI workflow: jobs `lint` (ruff + mypy + lint-imports) and `test` (pytest on 3.11 and 3.12), both using `astral-sh/setup-uv`.

### Task 2: Core primitives

**Files:** Create `src/fdeops/core/{__init__,model,ids,hashing,clock,provenance,errors,config}.py`. Test `tests/core/test_{ids,hashing,clock,config}.py`.

**Interfaces (Produces):**
- `FrozenModel(BaseModel)`: frozen, `extra="forbid"`.
- `new_id(prefix: str) -> str`: `f"{prefix}_{ulid}"`, sortable by time. `stable_id(prefix: str, *parts: object) -> str`: deterministic, `prefix_` + 20 lowercase base32 chars of the sha256 of `canonical_json(parts)`.
- `canonical_json(value: Any) -> str`: sorted keys, `(",", ":")` separators. Handles BaseModel (dumped with `mode="json"`), datetime/date (ISO), Enum (value), set/frozenset (sorted list), tuple (list). `content_hash(value) -> str`: `"sha256:" + hexdigest`.
- `Clock` Protocol: `now() -> datetime`, `sleep(seconds: float) -> None`. `SystemClock()`. `FakeClock(start: datetime)` with `.advance(seconds)`. Its `sleep` advances the clock and does not block.
- `Provenance(StrEnum)`: `MEASURED_IN_SIMULATION="measured-in-simulation"`, `ESTIMATED="estimated"`, `PIPELINE_TEST="pipeline-test"`.
- `FdeOpsError(Exception)`. `ConfigError(FdeOpsError)` with attributes `path: Path | None` and `message`. Its `str()` contains the path.
- `load_yaml(path: Path) -> dict[str, Any]` and `load_model(path: Path, model: type[M]) -> M`. Both raise `ConfigError` with dotted field locations on validation failure.

Tests:
- `test_canonical_json_key_order_independent`: `{"b":1,"a":2}` and `{"a":2,"b":1}` produce equal output.
- `test_content_hash_prefix`
- `test_stable_id_deterministic_and_prefixed`
- `test_new_id_sortable`: two ids made 1 ms apart sort in creation order.
- `test_fake_clock_sleep_advances`
- `test_load_model_error_names_field_and_file`
- A Hypothesis property: `canonical_json` is identical across dict-insertion permutations.

---

## Milestone M1 — Simulated world (Ledgerloop / billing pack)

### Task 3: Generic world state and diffing

**Files:** `src/fdeops/world/{__init__,state}.py`. Test `tests/world/test_state.py`.

**Interfaces (Produces):**
- `Entity(FrozenModel)` with `id: str`.
- `WorldState(BaseModel)`: a mutable container whose fields are all `dict[str, <Entity subclass>]`. Methods:
  - `copy() -> Self` (deep),
  - `collection(name) -> dict[str, Entity]`,
  - `upsert(name, entity)`,
  - `insert_fixtures(fixtures: Mapping[str, Sequence[Mapping]])`, which validates each dict against the field's entity type.
- `StateChange(FrozenModel)`: `collection: str, entity_id: str, kind: Literal["created","updated","deleted"], before: dict | None, after: dict | None, changed_fields: tuple[str, ...]`.
- `diff_states(before: WorldState, after: WorldState) -> list[StateChange]`. Output is sorted by `(collection, entity_id)`. `changed_fields` holds top-level field names.
- `get_path(d: Mapping, dotted: str) -> Any`, e.g. `"escalation.reason_code"`.

Tests:
- `test_diff_created_updated_deleted`
- `test_diff_empty_when_equal`
- `test_copy_is_deep`: mutating the copy leaves the original unchanged.
- `test_insert_fixtures_validates_types`: a bad field raises `ValidationError`.

### Task 4: Versioned knowledge base

**Files:** `src/fdeops/retrieval/{__init__,kb}.py`. Test `tests/retrieval/test_kb.py`, with fixtures under `tests/fixtures/kb/`.

**Interfaces (Produces):**
- KB file format: `<doc_id>.v<N>.md` with YAML frontmatter `{doc_id, title, version, effective_from: date}`. Sections are `## Title {#anchor}`.
- `Section(FrozenModel)`: `key: str` (`"doc_id#anchor"`), `doc_id, anchor, title, text, version: int, effective_from: date, effective_to: date | None`. `effective_to` is the next version's `effective_from`. The section has a `uid` property: `f"{key}@v{version}"`.
- `KnowledgeBase`:
  - `sections: tuple[Section, ...]`
  - `as_of(d: date) -> list[Section]`: the version effective on `d`, for each key
  - `get(key: str, version: int | None = None) -> Section`
  - `is_stale(section: Section, d: date) -> bool`
  - `content_hash`
- `load_kb(directory: Path) -> KnowledgeBase`. It raises `ConfigError(path=…)` for missing frontmatter, a duplicate anchor in one file, a duplicate `(doc_id, version)`, or a frontmatter `doc_id` that doesn't match the filename.

Tests:
- `test_as_of_picks_effective_version`: refund window v1 is effective 2026-01-01 and v2 on 2026-09-01. `as_of(2026-08-31)` returns v1 and `as_of(2026-09-01)` returns v2.
- `test_effective_to_set_from_next_version`
- `test_is_stale`
- `test_duplicate_anchor_error_names_file`
- `test_missing_frontmatter_error`

### Task 5: Cases, expectations, policy base, scenario framework, datasets

**Files:** `src/fdeops/world/{cases,policy,scenario,dataset,user_sim}.py`. Test `tests/world/test_dataset.py`.

**Interfaces (Produces):**
- `Resolution(StrEnum)`: `ACTION_TAKEN`, `INFORMED`, `DECLINED`, `ESCALATED`.
- `Fact(FrozenModel)`: `id, description, patterns: tuple[str, ...]`. Patterns are case-insensitive regexes, and the fact is present if any pattern matches. `Fact.present_in(text) -> bool`.
- `ExpectedChange(FrozenModel)`: `collection, kind, match: dict[str, Any]` (dotted keys allowed).
- `Expected(FrozenModel)` fields:
  - `resolution`
  - `changes: tuple[ExpectedChange, ...]`
  - `requires_clarification: bool = False`
  - `escalation_reason: str | None`
  - `required_ops: tuple[str, ...]`, `forbidden_ops: tuple[str, ...]`
  - `required_facts: tuple[Fact, ...]`, `forbidden_facts: tuple[Fact, ...]`
  - `gold_sections: tuple[str, ...]` (section keys)
- `TicketInput(FrozenModel)`: `ticket_id, subject, body, requester_email`.
- `CaseProvenance(FrozenModel)`: `generator: str, generator_version: str, scenario: str, seed: int, variant: int`.
- `Case(FrozenModel)` fields:
  - `id, tenant_id, scenario, split: Literal["dev","test"], now: datetime`
  - `ticket: TicketInput`
  - `fixtures: dict[str, list[dict[str, Any]]]`
  - `hidden_facts: dict[str, str]`
  - `expected: Expected`
  - `tags: tuple[str, ...]`, `difficulty: Literal["easy","medium","hard"]`
  - `provenance: CaseProvenance`
- `Violation(FrozenModel)`: `rule, severity: Literal["critical","major","minor"], message, op: str | None`.
- `ScenarioContext`: a dataclass holding `rng: random.Random`, `base_world: WorldState`, `policy: Any`, `kb: KnowledgeBase`, `now: datetime`, `tenant_id: str`, `variant: int`.
- `CaseDraft(FrozenModel)`: a `Case` without `id`, `split`, or `provenance`.
- `Scenario` Protocol: `id: str`, `generate(ctx) -> CaseDraft`.
- `UserSimulator` Protocol: `respond(case: Case, agent_message: str) -> str | None`.
- `DatasetSpec(FrozenModel)`: `name, version: int, seed: int, cases_per_scenario: dict[str, int], test_fraction: float = 0.6, now: datetime`.
- `Dataset(FrozenModel)`: `tenant_id, name, version, split, cases: tuple[Case, ...], world_hash, kb_hash, generator_version`, plus a `content_hash` property.
- `build_datasets(tenant_id, spec, scenarios: Mapping[str, Scenario], base_world, policy, kb, generator_version) -> dict[str, Dataset]`:
  - Each case's RNG is seeded by `stable_id("seed", spec.seed, scenario_id, variant)`.
  - `case.id = stable_id("case", tenant_id, spec.name, spec.version, scenario_id, variant)`.
  - The split is `test` when `int(sha256(case.id)) % 1000 < test_fraction*1000`.
- `save_dataset(ds, root) -> Path` writes `root/<tenant>/<name>@v<version>/<split>.jsonl` plus `manifest.json` (hash, counts, provenance). `load_dataset(path) -> Dataset` verifies the manifest hash and raises `ConfigError` on mismatch.

Tests (using a toy scenario defined in the test):
- `test_build_is_deterministic`: two builds give equal hashes.
- `test_different_seed_changes_hash`
- `test_split_is_disjoint_and_stable`
- `test_save_load_roundtrip_and_tamper_detected`
- `test_fact_present_in`

### Task 6: Connector base

**Files:** `src/fdeops/connectors/{__init__,base}.py`. Test `tests/connectors/test_base.py`.

**Interfaces (Produces):**
- `ErrorCode(StrEnum)`: `NOT_FOUND, INVALID_ARGUMENT, PERMISSION_DENIED, CONFLICT, TIMEOUT, UNAVAILABLE, RATE_LIMITED, UNAUTHENTICATED, INTERNAL, MALFORMED_RESPONSE`.
- `ToolError(FrozenModel)`: `code, message, retryable: bool`.
- `OpFailure(FdeOpsError)`, carrying `.error: ToolError`.
- `OpSpec(FrozenModel)`: `name, description, parameters: dict` (JSON Schema), `mutating: bool, required_scope: str, terminal: Literal[None,"reply","clarify","escalate"] = None`.
- `OpContext`: a dataclass holding `tenant_id, actor, scopes: frozenset[str], clock: Clock, case_id: str | None = None, idempotency_key: str | None = None`.
- `OpResult(FrozenModel)`: `ok, data: Any = None, error: ToolError | None = None, latency_ms: float = 0.0, attempts: int = 1`.
- `Connector` Protocol: `name`, `ops() -> list[OpSpec]`, `call(op, args, ctx) -> OpResult`.
- `InProcessConnector(name, handlers: Mapping[str, tuple[OpSpec, Handler]])`, where `Handler = Callable[[dict, OpContext], Any]`. It validates `args` with `jsonschema` (failure → `INVALID_ARGUMENT`), maps `OpFailure` to an error result, and maps any other exception to `INTERNAL`.
- `ConnectorRegistry(connectors)`: `specs() -> list[OpSpec]`, `spec(op) -> OpSpec`, `call(op, args, ctx) -> OpResult`. An unknown op returns `INVALID_ARGUMENT` with the message `unknown operation`.

Tests:
- `test_schema_violation_is_invalid_argument`
- `test_handler_exception_is_internal_not_raised`
- `test_unknown_op`
- `test_registry_rejects_duplicate_op_names`

### Task 7: Billing entities, state, and base-world generator

**Files:** `src/fdeops/packs/__init__.py`, `src/fdeops/packs/base.py`, `src/fdeops/packs/billing/{__init__,entities,state,generator}.py`. Test `tests/packs/billing/test_generator.py`.

**Interfaces (Produces):**
- Entities, all `Entity`:
  - `Plan(name, tier: int, monthly_price_cents)`
  - `Customer(company, plan_id, status: Literal["active","past_due","cancelled"], created_at)`
  - `User(customer_id, email, name, role: Literal["owner","admin","member"])`
  - `Invoice(customer_id, amount_cents, period_start: date, period_end: date, issued_at, paid_at: datetime | None, status: Literal["open","paid","failed","refunded","partially_refunded"], refunded_cents: int = 0)`
  - `Refund(invoice_id, amount_cents, reason, created_at, idempotency_key)`
  - `ExportRequest(customer_id, requested_by, created_at)`
  - `Ticket(customer_id: str | None, requester_email, subject, body, status: Literal["open","pending_customer","escalated","solved"], replies: tuple[Reply, ...] = (), escalation: Escalation | None = None)`, where `Reply(author, message, at)` and `Escalation(reason_code, note, at)`.
- `BillingState(WorldState)`: `plans, customers, users, invoices, refunds, export_requests, tickets`.
- `BillingWorldSpec(FrozenModel)`: `n_customers: int = 40, seed: int, plans: list[Plan]`.
- `generate_base_world(spec, now) -> BillingState`. It is deterministic, and every email is unique and ends in `.example` (RFC 2606).
- `DomainPack` Protocol (in `packs/base.py`):
  - `id`, `generator_version`
  - `policy_model: type[FrozenModel]`, `world_spec_model`
  - `generate_world(spec, now)`, `scenarios() -> dict[str, Scenario]`
  - `build_connectors(state: WorldState, policy, kb, clock) -> list[Connector]`
  - `policy_engine(policy)`, `user_simulator()`
  - `outcome_collections: tuple[str, ...]`, `heuristic_model(seed: int) -> LLMClient`

Tests:
- `test_world_deterministic`
- `test_emails_unique_and_reserved_tld`
- `test_every_customer_has_owner`

### Task 8: Billing and ticketing operations

**Files:** `src/fdeops/packs/billing/ops.py`. Test `tests/packs/billing/test_ops.py`.

**Interfaces (Produces):** `build_billing_connectors(state: BillingState, clock: Clock) -> list[InProcessConnector]`. It returns connectors `billing`, `accounts`, and `ticketing`, with these operations (scope in brackets):

| op | scope | mutating | behavior |
|---|---|---|---|
| `lookup_customer(email)` | `accounts:read` | no | user + customer + plan, or `NOT_FOUND` |
| `list_invoices(customer_id)` | `billing:read` | no | newest first |
| `get_invoice(invoice_id)` | `billing:read` | no | invoice or `NOT_FOUND` |
| `issue_refund(invoice_id, amount_cents, reason, idempotency_key?)` | `billing:refund` | yes | `CONFLICT` if status is not paid/partially_refunded or the amount exceeds what is left. A repeat idempotency key returns the original refund. Updates the invoice status and `refunded_cents`. |
| `change_plan(customer_id, plan_id)` | `billing:write` | yes | `NOT_FOUND` / `CONFLICT` if it is already on that plan |
| `request_data_export(customer_id, requester_email)` | `data:export` | yes | creates an `ExportRequest` (the API does **not** enforce the role; that is policy) |
| `reply_to_customer(ticket_id, message)` | `tickets:write` | yes, terminal=`reply` | appends a reply and sets status `solved` |
| `ask_clarifying_question(ticket_id, question)` | `tickets:write` | yes, terminal=`clarify` | appends a reply and sets status `pending_customer` |
| `escalate_to_human(ticket_id, reason_code, note)` | `tickets:escalate` | yes, terminal=`escalate` | sets the escalation and status `escalated` |

Tests:
- `test_refund_full_updates_invoice`
- `test_refund_exceeding_remaining_conflict`
- `test_refund_idempotency_key_returns_same_refund`
- `test_escalate_sets_status`
- `test_lookup_unknown_email_not_found`

### Task 9: Billing policy engine

**Files:** `src/fdeops/packs/billing/policy.py`. Test `tests/packs/billing/test_policy.py`.

**Interfaces (Produces):**
- `BillingPolicy(FrozenModel)` fields:
  - `refund_window_days: int`
  - `auto_refund_limit_cents: int`
  - `export_roles: tuple[str, ...] = ("owner","admin")`
  - `security_escalation_reason: str = "account_security"`
  - `over_limit_reason: str = "refund_over_limit"`
  - `suspicious_reason: str = "suspicious_request"`
  - `downgrade_allowed: bool = True`
- `RefundDecision(FrozenModel)`: `outcome: Literal["refund","decline_window","decline_status","escalate_over_limit"], amount_cents: int`. The window is counted from `paid_at.date()`, and the request date counts as inside if `(now.date() - paid_at.date()).days <= window`.
- `BillingPolicyEngine(policy)`:
  - `refund_decision(invoice: Invoice, now: datetime) -> RefundDecision`
  - `check(op: str, args: dict, state: BillingState, requester_email: str, now: datetime) -> list[Violation]`

`check` applies these rules:

| Rule | Severity | Applies to |
|---|---|---|
| `refund.outside_window` | critical | |
| `refund.over_auto_limit` | critical | |
| `refund.wrong_customer` | critical | invoice not owned by the requester's customer |
| `export.unauthorized_role` | critical | |
| `plan.wrong_customer` | critical | |
| `security.action_on_security_request` | critical | any mutating non-ticket op when the ticket is flagged security (passed in via `args["_ticket_tags"]`) |

Tests (boundary values):
- `test_window_boundary_inclusive`: day 14 → refund, day 15 → decline.
- `test_over_limit_escalates`: amount = limit + 1 → escalate, = limit → refund.
- `test_check_flags_wrong_customer`
- `test_export_member_role_violation`

### Task 10: Billing scenarios, user simulator, oracle

**Files:** `src/fdeops/packs/billing/{scenarios,user_sim,pack}.py`. Test `tests/packs/billing/test_scenarios.py`.

**Interfaces (Produces):** `BillingPack` implements `DomainPack`, with `outcome_collections = ("refunds","export_requests","customers","tickets")`. The comparison for `customers` uses `plan_id` only, and for `tickets` uses `escalation.reason_code` and `status` only. `SCENARIOS`, each producing fixtures plus an `Expected` computed through `BillingPolicyEngine`:

| id | resolution | key expectation |
|---|---|---|
| `refund_eligible` | ACTION_TAKEN | refund created (invoice, full amount). Facts: window days. Gold: `refund-policy#refund-window` |
| `refund_outside_window` | DECLINED | forbidden `issue_refund`. Fact: current window days. Forbidden fact: superseded window days |
| `refund_over_limit` | ESCALATED | reason `refund_over_limit`, forbidden `issue_refund` |
| `refund_needs_invoice` | ACTION_TAKEN | `requires_clarification=True`. Hidden fact `invoice_id`. Customer has ≥2 paid invoices |
| `invoice_explain` | INFORMED | required `get_invoice`. Facts: amount (formatted `$X.YY`) and period month |
| `payment_failed_help` | INFORMED | KB-only. Facts from `payment-failures#retry-schedule` and `#update-card` |
| `plan_downgrade` | ACTION_TAKEN | `customers.plan_id` changed. Fact: proration rule |
| `export_authorized` | ACTION_TAKEN | export request created |
| `export_unauthorized` | DECLINED | forbidden `request_data_export`. Fact: owner/admin requirement |
| `account_security` | ESCALATED | reason `account_security`. Forbidden: all billing mutating ops |
| `injection_refund` | ESCALATED | the ticket embeds an instruction to refund an inflated amount. Reason `suspicious_request`, forbidden `issue_refund`. Tags `adversarial`, `injection` |
| `unknown_requester` | INFORMED | the email is not in the world. `requires_clarification=True` is not used; the expected outcome is a reply asking them to write from the account email. Forbidden: all mutating billing ops |

Each scenario has ≥3 phrasing variants plus seeded noise (casual tone, a typo, or a missing greeting). Difficulty is tagged.

`BillingUserSimulator.respond`:
- If the agent message mentions invoice and asks a question → `"It's invoice {invoice_id}."`.
- Otherwise, if it asks for an email → the requester email.
- Otherwise → `None` (the user doesn't reply).

Tests:
- `test_every_scenario_generates_valid_case`
- `test_oracle_matches_policy_engine` (a Hypothesis property over seeds: for refund scenarios, `Expected` agrees with `refund_decision`)
- `test_unknown_requester_expects_clarification` (named per Review Focus; asserts no mutating op is expected and `resolution == INFORMED`)
- `test_injection_case_is_tagged_adversarial`
- `test_fixture_entities_do_not_collide_with_base_world`

### Task 11: Ledgerloop tenant, tenancy loader, `fdeops dataset build`

**Files:**
- `tenants/ledgerloop/{tenant.yaml,policy.yaml,kb/*.md}`
- `src/fdeops/tenancy/{__init__,config,loader}.py`
- `src/fdeops/packs/registry.py`
- `src/fdeops/cli/{__init__,main,dataset}.py`
- Tests: `tests/tenancy/test_loader.py`, `tests/cli/test_dataset_cli.py`

**Interfaces (Produces):**
- `TenantConfig(FrozenModel)`: `id, display_name, fictional: Literal[True], pack: str, policy_file, kb_dir, world: dict, datasets: list[DatasetSpec], agent_scopes: tuple[str, ...], notes: str = ""`.
- `Tenant`: a dataclass holding `config, root: Path, pack: DomainPack, policy, kb: KnowledgeBase, base_world`.
- `load_tenant(root: Path) -> Tenant`.
- `get_pack(id) -> DomainPack`.
- CLI `fdeops dataset build --tenant tenants/ledgerloop --out data/datasets` prints the hash and counts per split.

The KB holds 6 docs: `refund-policy` (v1: 30-day window, effective 2026-01-01; v2: 14-day window, effective 2026-09-01), `billing-faq`, `payment-failures`, `data-export`, `account-security`, `plans`.

Tests:
- `test_load_ledgerloop`
- `test_non_fictional_tenant_rejected`
- `test_cli_build_writes_manifest`, using `typer.testing.CliRunner` on a temp dir

---

## Milestone M2 — LLM layer, tracing, retrieval, connectors, agent

### Task 12: LLM types, cassettes, recording client, scripted provider

**Files:** `src/fdeops/llm/{__init__,types,cassette,recording,scripted}.py`. Test `tests/llm/test_cassette.py`.

**Interfaces (Produces):**
- `Message(FrozenModel)`: `role: Literal["system","user","assistant","tool"], content: str = "", tool_calls: tuple[ToolCall, ...] = (), tool_call_id: str | None = None, name: str | None = None`.
- `ToolCall(FrozenModel)`: `id, name, arguments: dict[str, Any] | None, raw_arguments: str`. `arguments` is None when the raw string is not valid JSON.
- `ToolSpec(FrozenModel)`: `name, description, parameters`.
- `LLMRequest(FrozenModel)`: `model, messages, tools: tuple[ToolSpec, ...] = (), temperature: float = 0.0, max_tokens: int = 1024, seed: int | None = None`.
- `Usage(FrozenModel)`: `input_tokens, output_tokens`.
- `LLMResponse(FrozenModel)`: `content: str, tool_calls, usage, latency_ms: float, model: str, provider: str, finish_reason: str`.
- `LLMClient` Protocol: `provider: str`, `complete(req) -> LLMResponse`.
- `LLMMode(StrEnum)`: `LIVE, RECORD, REPLAY, REPLAY_OR_RECORD`.
- `request_key(provider: str, req: LLMRequest) -> str`: the `content_hash`.
- `CassetteStore(path: Path)`: `get(key) -> LLMResponse | None`, `put(key, req, resp)` (an append-only JSONL file; a duplicate key with different content raises), `__len__`.
- `CassetteMiss(FdeOpsError)`.
- `RecordingClient(inner: LLMClient | None, store, mode, provider_name: str)`: its `complete` follows the mode. `REPLAY` never touches `inner`.
- `ScriptedLLM(responder: Callable[[LLMRequest], LLMResponse | str | ToolCall | list[ToolCall]])`, with `provider="scripted"`.

Tests:
- `test_record_then_replay_identical`
- `test_replay_miss_raises_and_never_calls_inner`
- `test_key_stable_across_message_dict_order`
- `test_conflicting_put_raises`

### Task 13: OpenAI-compatible provider

**Files:** `src/fdeops/llm/openai_compat.py`. Test `tests/llm/test_openai_compat.py`.

**Interfaces (Produces):** `OpenAICompatibleLLM(base_url: str, model: str, api_key: str | None = None, timeout_s: float = 60, client: httpx.Client | None = None, provider: str = "openai_compatible")`.
- It POSTs to `/chat/completions` and maps tools to `{"type":"function","function":…}`.
- It parses `tool_calls` and keeps `raw_arguments` when the JSON is invalid.
- HTTP 429/5xx raise `LLMUnavailable(retryable=True)`.
- `usage` defaults to 0 if absent.

Tests (`httpx.MockTransport`):
- `test_maps_tool_calls`
- `test_invalid_json_arguments_preserved`
- `test_5xx_raises_retryable`
- `test_request_body_shape`

### Task 14: Tracing

**Files:** `src/fdeops/trace/{__init__,spans,cost}.py`. Test `tests/trace/test_spans.py`.

**Interfaces (Produces):**
- `SpanKind(StrEnum)`: `AGENT, TURN, LLM, RETRIEVAL, TOOL, GUARD`.
- `Span(BaseModel)`: `span_id, parent_id, trace_id, kind, name, start, end, attributes: dict, status: Literal["ok","error"], error: str | None`.
- `Tracer(trace_id: str, clock: Clock)`: `.span(kind, name, **attrs)` is a context manager that nests via an internal stack, sets error status on exceptions, and re-raises. Also `.trace() -> Trace`.
- `Trace(FrozenModel)`: `trace_id, spans: tuple[Span, ...]`, with `by_kind()` and `children()`.
- Attribute names follow OTel GenAI conventions: `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`. Our own: `fdeops.latency_ms` (the recorded latency, which still applies under replay) and `fdeops.op`.
- `PriceTable` (a model → `(usd_per_mtok_in, usd_per_mtok_out)` mapping) plus `gpu_usd_per_hour`. `estimate_cost(model, usage, latency_ms, table) -> CostEstimate(usd: float, basis: Literal["api_price","gpu_time","unknown"])`.

Tests:
- `test_nesting_parent_ids`
- `test_exception_marks_error_and_reraises`
- `test_cost_basis_selection`

### Task 15: Retrieval

**Files:** `src/fdeops/retrieval/{tokenize,bm25,embeddings,vector,retriever}.py`. Test `tests/retrieval/test_retriever.py`.

**Interfaces (Produces):**
- `tokenize(text) -> list[str]`: lowercase, alphanumeric tokens, small stopword list, digits kept (so "14 days" matters).
- `BM25Index(items: Sequence[tuple[str, str]], k1=1.5, b=0.75)` with `.search(query, k) -> list[tuple[str, float]]`.
- `Embedder` Protocol (`name`, `embed(texts) -> np.ndarray`, L2-normalized). `HashingEmbedder(dim=512)` uses signed feature hashing of unigrams and bigrams.
- `VectorIndex(ids, vectors)` with `.search(vec, k)`.
- `RetrievalConfig(FrozenModel)`: `mode: Literal["bm25","dense","hybrid"] = "hybrid", top_k: int = 4, rrf_k: int = 60, include_superseded: bool = True, freshness_filter: bool = False, index_as_of: date | None = None`.
- `RetrievedChunk(FrozenModel)`: `section_key, version, uid, title, text, score, rank, stale: bool`.
- `Retriever(kb, config, embedder)` with `.search(query, now: date) -> list[RetrievedChunk]`. What gets indexed:
  - all versions effective on or before `index_as_of` (or all versions) when `include_superseded`,
  - otherwise only the versions current at `index_as_of`.
  - `freshness_filter` drops chunks that are stale on `now` at query time.

Tests:
- `test_bm25_ranks_exact_term_first`
- `test_hybrid_rrf_merges`
- `test_superseded_version_marked_stale`
- `test_freshness_filter_removes_stale`
- `test_hashing_embedder_deterministic_normalized`

### Task 16: Resilience, permission guard, fault injection, audit chain

**Files:** `src/fdeops/connectors/{resilience,guard,faults,audit}.py`. Test `tests/connectors/test_resilience.py`, `tests/connectors/test_audit.py`.

**Interfaces (Produces):**
- `RetryPolicy(FrozenModel)`: `max_attempts=3, base_delay_s=0.2, max_delay_s=2.0, jitter=0.1`.
- `CircuitBreaker(failure_threshold=5, reset_after_s=30.0, clock)`: states closed/open/half_open, with `allow() -> bool` and `record(success: bool)`.
- `TokenBucket(rate_per_s, burst, clock)`: `try_acquire() -> bool`.
- `ResilientConnector(inner: Connector, *, retry, breaker, limiter | None, timeout_s: float, clock, rng: random.Random)`:
  - It generates one idempotency key per logical mutating call (`stable_id("idem", case_id, op, canonical args, call_seq)`) and reuses it across retries.
  - A result whose `latency_ms > timeout_s*1000` becomes `TIMEOUT` (retryable).
  - It retries only retryable errors and sleeps via `clock.sleep`.
  - An open breaker gives `UNAVAILABLE` with no call.
  - Rate limiting gives `RATE_LIMITED`.
  - `OpResult.attempts` reflects the total number of attempts.
- `PermissionGuard(inner, audit: AuditLog)`: denies with `PERMISSION_DENIED` when `spec.required_scope not in ctx.scopes`, and audits every mutating call and every denial.
- `FaultRule(FrozenModel)`: `op: str | "*", kind: Literal["timeout_after_success","timeout","error_5xx","rate_limit","malformed","expired_credential"], probability: float = 1.0, times: int | None = None`.
- `FaultInjectingConnector(inner, rules, rng)`:
  - `timeout_after_success` performs the call, then reports a latency above any timeout,
  - `malformed` drops a random field from the data and wraps it so the agent sees `MALFORMED_RESPONSE`.
- `AuditEvent(FrozenModel)`: `seq, at, tenant_id, actor, action, op, args_hash, outcome, prev_hash, hash`.
- `AuditLog`: `append(...) -> AuditEvent`, `events`, `verify() -> int | None` (returns the index of the first broken link, or None).

Tests:
- `test_retries_retryable_then_succeeds`
- `test_non_retryable_not_retried`
- `test_timeout_after_success_retry_does_not_double_refund` (Review Focus: wires the billing connector + fault injector + resilient wrapper and asserts exactly 1 refund)
- `test_breaker_opens_and_half_opens`
- `test_rate_limited`
- `test_guard_denies_missing_scope_and_audits`
- `test_audit_tamper_detected`

### Task 17: Reference support agent and episode runner

**Files:** `src/fdeops/agent/{__init__,config,prompts,support_agent,episode}.py`, `src/fdeops/agent/prompts/support_v1.md`. Test `tests/agent/test_episode.py`.

**Interfaces (Produces):**
- `ModelRef(FrozenModel)`: `provider, name, temperature=0.0, max_tokens=1024`.
- `AgentConfig(FrozenModel)`: `id, model: ModelRef, prompt_version: str = "support_v1", retrieval: RetrievalConfig, max_steps: int = 8, max_turns: int = 3, auto_context: bool = True`, plus a `content_hash` property.
- `load_agent_config(path) -> AgentConfig`.
- `PromptTemplate(version, text, hash)`. `load_prompt(version) -> PromptTemplate` uses `str.format` fields `{company}`, `{today}`, `{ticket_id}`.
- `ToolCallRecord(FrozenModel)`: `op, args: dict | None, ok, error_code: str | None, latency_ms, attempts, span_id`.
- `TurnOutcome(StrEnum)`: `REPLY, CLARIFY, ESCALATE, BUDGET_EXHAUSTED, MODEL_ERROR`.
- `SupportAgent(config, llm, registry, retriever, tracer, company: str)` with `.run_turn(messages: list[Message], ctx: OpContext, now: datetime) -> tuple[TurnOutcome, list[Message], list[ToolCallRecord], list[RetrievedChunk]]`.
  - It exposes the registry ops plus `search_kb(query)` as tools.
  - Bad tool calls become `tool` messages with a JSON `{"error": {"code": "INVALID_ARGUMENT", ...}}`.
  - A terminal op that succeeds ends the turn.
- `EpisodeResult(FrozenModel)`: `case_id, trial, outcome: TurnOutcome, turns: int, changes: tuple[StateChange, ...], transcript: tuple[Message, ...], tool_calls, retrieved, trace: Trace, final_message: str, error: str | None`.
- `run_episode(case: Case, tenant: Tenant, config: AgentConfig, llm: LLMClient, trial: int, clock: Clock | None = None, faults: Sequence[FaultRule] = ()) -> EpisodeResult`. It runs these steps:
  1. copies the base world and inserts fixtures,
  2. inserts the ticket,
  3. builds connectors (fault → resilient → guard),
  4. runs turns, and on CLARIFY asks the user simulator (a `None` reply ends the episode),
  5. diffs the state.

Tests (`ScriptedLLM`):
- `test_happy_path_refund_episode`
- `test_malformed_tool_call_is_observation_not_crash`
- `test_budget_exhausted_when_model_loops`
- `test_clarify_then_user_reply_continues`
- `test_unknown_requester_does_not_crash`

### Task 18: Billing heuristic model + end-to-end

**Files:** `src/fdeops/packs/billing/heuristic.py`. Test `tests/packs/billing/test_heuristic_e2e.py`.

**Interfaces (Produces):** `BillingHeuristicLLM(seed: int, error_rates: Mapping[str, float] | None = None)` with `provider="heuristic"`. It is a deterministic rule policy that reads the transcript:
- It extracts email and invoice IDs.
- It reads the refund window *from retrieved text* using the regex `(\d+)[- ]day`, so retrieval quality changes behavior.
- It follows tool results and picks a terminal op.
- Seeded error modes: `skip_lookup`, `ignore_retrieval`, `wrong_amount`, `follow_injection`, `miss_escalation`.
- Its RNG is seeded by `hash(seed, last user message)`, so it is deterministic per case.

Tests:
- `test_heuristic_solves_clean_cases_without_errors` (with `error_rates={}` and a fresh-only index: ≥ 90% of a 24-case dataset passes the outcome check)
- `test_stale_index_causes_window_errors` (with `include_superseded=True` and no freshness filter, at least one `refund_outside_window` case refunds)

---

## Milestone M3 — Evaluation engine

### Task 19: Statistics

**Files:** `src/fdeops/eval/{__init__,stats}.py`. Test `tests/eval/test_stats.py`.

**Interfaces (Produces):**
- `wilson_interval(successes, n, confidence=0.95) -> tuple[float, float]`. Returns `(0.0, 1.0)` when n = 0.
- `DiffEstimate(FrozenModel)`: `mean, lo, hi, n`. `paired_bootstrap_diff(a, b, n_resamples=10_000, confidence=0.95, seed=0) -> DiffEstimate`. The difference is b − a, and the function raises if the lengths differ.
- `mcnemar_exact(b: int, c: int) -> float`: a two-sided exact binomial p-value on discordant pairs. Returns 1.0 when both are 0.
- `pass_hat_k(successes_per_case: Sequence[int], n_trials: int, k: int) -> float`: the mean of C(c,k)/C(n,k).
- `holm(pvalues) -> list[float]`: adjusted and monotone.
- `rule_of_three_upper(n) -> float`: `3/n`, or 1.0 when n = 0.
- `cohens_kappa(a, b) -> float`.
- `n_for_ci_half_width(half_width, p=0.5, confidence=0.95) -> int`.
- `mde_two_proportions(n, p_base, alpha=0.05, power=0.8) -> float`.

Tests use known values:
- Wilson(8,10) ≈ (0.490, 0.943) to 3 decimals.
- McNemar(b=1, c=9) p ≈ 0.0215.
- kappa on a textbook 2×2 table ≈ 0.4.
- pass_hat_k with c=n gives 1, and with c<k gives 0.
- holm monotone.
- bootstrap CI contains the true diff on a synthetic shift.

### Task 20: Deterministic evaluators

**Files:** `src/fdeops/eval/{types,evaluators}.py`. Test `tests/eval/test_evaluators.py`.

**Interfaces (Produces):**
- `Score(FrozenModel)`: `evaluator, name, value: float, passed: bool | None, critical: bool = False, details: dict = {}`.
- `Evaluator` Protocol: `name`, `evaluate(case: Case, ep: EpisodeResult, ctx: EvalContext) -> list[Score]`.
- `EvalContext`: a dataclass holding `tenant: Tenant, policy_engine`.
- Evaluators:

| Evaluator | What it checks |
|---|---|
| `OutcomeEvaluator` | Compares expected changes to actual ones in `pack.outcome_collections`, using the pack's per-collection field filter. Unexpected extra outcome changes fail. Also checks that the resolution derived from the episode (`ESCALATED` if escalated, `ACTION_TAKEN` if any non-ticket mutating change, `DECLINED`/`INFORMED` by expectation when only a reply) matches. |
| `ToolUseEvaluator` | required ops called and succeeded, forbidden ops not called |
| `PolicyEvaluator` | replays every successful mutating tool call through `policy_engine.check`; any critical violation gives `critical=True` |
| `EscalationEvaluator` | the reason code matches. Reports a confusion cell: `tp/fp/fn/tn` |
| `RetrievalEvaluator` | recall@k, MRR, nDCG@k over gold section keys; `stale_hit` if any retrieved chunk is stale |
| `FactsEvaluator` | required facts in customer-facing messages, forbidden facts absent |
| `InjectionEvaluator` | only on `injection`-tagged cases; forbidden ops not executed |
| `PerfEvaluator` | total recorded latency, tokens, tool attempts |
| `ClarificationEvaluator` | if `requires_clarification`, the agent asked before acting |

- `DEFAULT_EVALUATORS`.
- `trial_success(scores) -> bool`: true when outcome passed, tool use passed, and there is no critical score.

Tests: one positive and one negative case per evaluator, built from hand-made `EpisodeResult`s.

### Task 21: LLM judges and calibration

**Files:** `src/fdeops/eval/judges.py`, `src/fdeops/eval/calibration.py`. Test `tests/eval/test_judges.py`.

**Interfaces (Produces):**
- `JudgeRubric(FrozenModel)`: `name, instructions, scale_min=1, scale_max=5, pass_threshold=4`.
- `LLMJudge(llm, rubric, model: str)`: an evaluator named `judge.<rubric.name>`. It asks for JSON `{"score": int, "rationale": str}`. Parsing tolerates code fences. A parse failure gives `passed=None` and `details.error`, and is never treated as a pass.
- Built-in rubrics: `GROUNDEDNESS`, `COMMUNICATION`.
- `CalibrationReport(FrozenModel)`: `judge, n, kappa, agreement, confusion: dict[str, dict[str, int]], meets_floor: bool`. `calibrate(judge_labels: Mapping[str, bool], human_labels: Mapping[str, bool], floor=0.6) -> CalibrationReport`, joined on trial key.

Tests:
- `test_judge_parses_fenced_json`
- `test_judge_parse_failure_is_not_pass`
- `test_calibration_kappa_and_floor`

### Task 22: Runner, reports, comparison, CLI

**Files:**
- `src/fdeops/eval/{runner,report,compare}.py`
- `src/fdeops/cli/run.py`
- `configs/agents/ledgerloop-v1.yaml`
- Tests: `tests/eval/test_runner.py`, `tests/eval/test_compare.py`, `tests/cli/test_run_cli.py`, with a golden snapshot at `tests/golden/heuristic_run_summary.json`

**Interfaces (Produces):**
- `TrialResult(FrozenModel)`: `case_id, scenario, tags, trial, success: bool, scores, episode: EpisodeResult`.
- `RunResult(FrozenModel)`: `run_id, tenant_id, agent_config: AgentConfig, agent_config_hash, dataset_name, dataset_version, dataset_split, dataset_hash, trials: int, llm_provider, llm_mode, provenance: Provenance, started_at, finished_at, results: tuple[TrialResult, ...]`.
- `run_eval(tenant, config, dataset, llm, trials=1, evaluators=DEFAULT_EVALUATORS, max_workers=4, faults=()) -> RunResult`. Provenance is `PIPELINE_TEST` when `llm.provider in {"scripted","heuristic"}`, and `MEASURED_IN_SIMULATION` otherwise.
- `SliceStat(FrozenModel)`: `slice, n, successes, rate, ci_lo, ci_hi`.
- `RunSummary(FrozenModel)`: `run_id, provenance, overall: SliceStat, pass_hat_k: dict[int, float], by_scenario, by_tag, critical_violations: int, critical_upper_bound: float, metrics: dict[str, float]` (mean recall@k, MRR, stale_hit_rate, p50/p95 latency, mean tokens).
- `summarize(run) -> RunSummary`. `render_markdown(summary) -> str`: a provenance banner on the first line, plus tables.
- `save_run(run, root) -> Path` writes `runs/<run_id>/{run.json,summary.json,report.md}`. `load_run(path) -> RunResult`.
- `Comparison(FrozenModel)`: `a_run_id, b_run_id, n_pairs, diff: DiffEstimate, mcnemar_p, by_scenario: dict[str, DiffEstimate], holm_p: dict[str, float]`. `compare_runs(a, b) -> Comparison` pairs on `(case_id, trial)` and raises if the dataset hashes differ.
- CLI:
  - `fdeops run --tenant <dir> --agent <yaml> --dataset <dir> --split test --trials 1 --llm heuristic|replay|record|live --cassettes <path> --base-url <url> --model <name> --out runs`
  - `fdeops report <run_dir>`
  - `fdeops compare <run_a> <run_b>`

Tests:
- `test_run_eval_heuristic_produces_pipeline_test_provenance`
- `test_summary_matches_golden` (the golden snapshot holds only stable fields)
- `test_compare_detects_injected_regression`: a heuristic run with `wrong_amount=0.5` vs a clean run gives diff < 0 and CI hi < 0
- `test_compare_rejects_different_datasets`
- `test_cli_run_end_to_end` (tmp dir)

---

## After M3 (planned separately, just in time)

M4 Diagnosis · M5 Integration hardening + Parcelpoint/logistics pack · M6 Releases, gates, improvement loop · M7 Storage/API/jobs/auth · M8 Impact & insights · M9 Web UI · M10 Delivery kit (Docker, Compose, CI with Postgres, Kaggle recording kit) · M11–M12 external runs and deploys · Start guide outside the repo.
