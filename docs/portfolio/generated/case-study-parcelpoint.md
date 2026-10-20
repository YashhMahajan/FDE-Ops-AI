> **Provenance: pipeline-test**. A stand-in model made these numbers. They test the pipeline. They do not measure the quality of an agent.

# Case Study: The Parcelpoint (fictional) Deployment

*Language: ASD-STE100. The platform wrote this document from the tenant files and the records of the flagship demo. The company and its data are fictional.*

## The customer

Parcelpoint (fictional) is the second tenant on the platform. It uses the `logistics` domain pack. Moderate risk tolerance, high volume, and latency is important. The claim auto-approval limit decreased from $500 to $300 on 2026-09-10 (claims v2). Legal words in a ticket always go to the legal team.

## What the deployment needed

| item | value |
|---|---:|
| Configuration files (YAML) | 6 |
| Lines in the configuration files | 154 |
| Knowledge base documents | 7 |
| Domain pack: lines of Python | 1385 |
| Platform: lines of Python (not in packs) | 11416 |
| Platform files that name a tenant | 0 |
| Scenarios in the pack | 11 |
| Incident files | 2 |

The platform code did not change for this tenant. A new domain needs a pack. A new tenant in a known domain needs only the configuration files.

## Differences from the first tenant

| setting | Ledgerloop (fictional) | Parcelpoint (fictional) |
|---|---|---|
| minimum lower limit of task success | 85% | 80% |
| maximum critical trials | 0 | 0 |
| maximum p95 latency (ms) | 8,000 | 4,000 |
| maximum cost for each resolution | $0.05 | $0.02 |
| monitors | 9 | 7 |
| CUSUM alarm level | 3.0 | 4.0 |
| PII patterns of the tenant | 0 | 2 |
| agent scopes | 8 | 7 |

## Data quality at ingest

The ingest step loaded 243 records and isolated 0. It found 0 issue(s). Each issue tells the record, the field and the cause.

## Result

- **v1 goes to production.** v1 passed 8 of 8 gates. Status: approved.
- **Incident: claims-limit-drift.** The claims limit change is published, but the previous section stays in the index. The production monitor gave 3 alert(s): critical_flag, policy_flag, stale_context. The first alarm (stale_context) came after 8 ticket(s). The monitor saw 8 of 8 failures. 0 failure(s) were silent.
- **Regression measured.** An evaluation of v1 during the incident: success changed by -0.121 (95% CI -0.212 to -0.045). The largest change is in damage_claim_large (-0.571).
- **Diagnosis.** The largest cluster is stale_knowledge:damage_claim_large (8 trials). Verdict: confirmed by intervention. freshness_filter fixed 8 of 8 cases with 0 regressions in 20 control cases.
- **v2 with the fix.** Fix: freshness_filter. The loop stopped at pending_approval. Then a person with the approver role approved it. Dev change: +0.167. After the fix, the monitor gives 0 alert(s).
- **Business value.** Savings for each month against a person only: median $112,367 (5th to 95th percentile $62,114 to $164,128). These values use assumptions.

## Lessons

- Tenant settings in files make the differences easy to examine in a review.
- The same incident type (document drift) occurred at the two tenants. The same monitor, the same diagnosis and the same fix found it.
- A second tenant is the test of a multi-tenant design. Tenant names in platform code show a design defect. A test finds them.
