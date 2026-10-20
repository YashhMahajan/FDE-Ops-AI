# M5: Integrations and a Second Tenant

*Design: sections 5.2, 5.5 and 5.14.*

**Goal.** Show that the platform is a product and not one demo. A second tenant in a different domain must use the same platform with configuration only. Incidents must be files that a person can run again. Bad data must give a report, not a failure.

## Global constraints

- All M0 to M4 constraints apply.
- The logistics pack and the billing pack use the same ticket code (`packs/common`).
- An incident is a YAML file. The run record keeps the full incident specification.
- PII redaction occurs after the evaluators run, before the platform keeps a trace. Thus, the scores use the real text, and the stored trace does not keep the PII.
- The ingest step does not remove a bad record without a report.

## Tasks

| Task | Scope | Files | Tests |
|---|---|---|---|
| 1 | Shared ticket entities and ticket operations | `packs/common/tickets.py` | current tests |
| 2 | Ingest with validation, normalization, integrity checks and a data-quality report | `world/ingest.py` | `tests/world/test_ingest.py` |
| 3 | PII redaction of traces and transcripts | `trace/redact.py`, `eval/runner.py` | `tests/trace/test_redact.py` |
| 4 | Incident files: API faults, document drift, prompt injection, model change, retrieval change, schema change, data quality | `incidents/`, `world/incidents.py`, `eval/runner.py` | `tests/eval/test_incidents.py` |
| 5 | Logistics pack: entities, APIs, policy, scenarios, heuristic model | `packs/logistics/` | `tests/packs/logistics/` |
| 6 | Parcelpoint tenant with different policy, risk and PII rules | `tenants/parcelpoint/` | `tests/tenancy/` |
| 7 | External agent adapter for Python agents | `agent/external.py` | `tests/agent/test_external.py` |
| 8 | REST connector with a field map | `connectors/rest.py` | `tests/connectors/test_rest.py` |

## Review items

| Failure mode | Correct behavior | Test |
|---|---|---|
| A record without a necessary field | The ingest step isolates the record and the report gives the field and the cause | `test_invalid_record_is_quarantined_with_reason` |
| A record that refers to an unknown customer | The ingest step isolates it as an integrity error | `test_orphan_record_is_integrity_error` |
| An email address in a ticket, a tool argument and a reply | The stored run does not contain it. The facts score was calculated before the redaction. | `test_stored_run_has_no_pii_but_scores_used_raw_text` |
| An incident file with an unknown type | A `ConfigError` names the file | `test_unknown_incident_kind_names_file` |
| Two tenants in one run folder | Each run record has its own tenant ID, and a comparison of two tenants stops | `test_compare_rejects_runs_of_two_tenants` |
