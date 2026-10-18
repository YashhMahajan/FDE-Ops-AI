# M8: Business Impact and Product Intelligence

*Language: ASD-STE100. Refer to the [glossary](../glossary.md). Design: sections 5.12 and 5.13.*

**Goal.** Change model metrics into business decisions. Calculate the value of a deployment against two baselines, with its uncertainty. Change failure clusters into ranked product opportunities with evidence, and write a roadmap memo.

## Global constraints

- All M0 to M7 constraints apply.
- Each number in an impact report has a label: `measured` (from a run) or `assumption` (from the tenant cost file).
- Each assumption has a low value, a likely value, a high value and a source.
- The ROI result is a distribution, not one number. The report gives the 5th, 50th and 95th percentiles and the probability that the savings are more than zero.
- One baseline is human only. The other baseline is a simple FAQ responder without an LLM. The platform runs the FAQ baseline as an external agent, thus its numbers are measured.
- The report shows the rank formula of each opportunity and each input of the formula.

## Tasks

| Task | Scope | Files | Tests |
|---|---|---|---|
| 1 | Cost model with ranges and sources for each tenant | `impact/costs.py`, `tenants/*/costs.yaml` | `tests/impact/test_costs.py` |
| 2 | Measured rates for each category from a run | `impact/measure.py` | `tests/impact/test_measure.py` |
| 3 | FAQ baseline agent | `impact/baseline.py` | `tests/impact/test_baseline.py` |
| 4 | ROI with a Monte Carlo simulation | `impact/roi.py`, `impact/report.py` | `tests/impact/test_roi.py` |
| 5 | Opportunities from diagnosis and impact, with effort estimates | `insights/opportunities.py`, `tenants/*/effort.yaml` | `tests/insights/test_opportunities.py` |
| 6 | Roadmap memo | `insights/roadmap.py` | `tests/insights/test_roadmap.py` |
| 7 | CLI and API: `fdeops impact`, `fdeops opportunities` | `cli/impact.py`, `api/app.py` | `tests/cli/test_impact_cli.py` |

## Review items

| Failure mode | Correct behavior | Test |
|---|---|---|
| An assumption without a range | The cost file does not load | `test_assumption_needs_range` |
| A category with no trials | The report uses the default category and tells this | `test_unknown_category_uses_default` |
| A run with the label `pipeline-test` | The ROI report keeps that label on the first line | `test_roi_report_keeps_pipeline_label` |
| An opportunity with an `inconclusive` verdict | It gets a low confidence and it goes to the list of items that we do not build | `test_inconclusive_goes_to_not_build` |
| An effort estimate of zero | The file does not load | `test_effort_must_be_positive` |
