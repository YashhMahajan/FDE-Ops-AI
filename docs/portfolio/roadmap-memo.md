# Roadmap Memo: The Next Two Milestones

*Owner: the product manager of the platform. Readers: the platform team and the FDE team.*

## Decision

We build four items next, in this sequence:

1. Real model runs and a benchmark with real numbers (milestone M11).
2. A gate that examines the index for superseded sections.
3. Enforce mode for critical policy rules, for each tenant.
4. A review queue for tickets without a flag.

We do not build fine-tuning, a multi-agent system or Kubernetes support in these milestones.

## Why these items

### 1. Real model runs

All results at this time have the label `pipeline-test`. They prove that the platform operates. They do not prove that it finds failures of a real model. A real model makes failures that the stand-in model does not make, for example `grounding_failure` and `bad_arguments`. Without real runs, each claim to a customer is weak.

- Evidence: the [benchmark report](generated/benchmark-report.md). Each row has the label `pipeline-test`.
- Effort: about one week. The [recording kit](../guides/real-model-runs.md) is complete. The cost is zero with free models and a free Kaggle GPU.
- Measure of success: the benchmark report with the label `measured-in-simulation` for the two tenants.

### 2. A gate for superseded sections in the index

The same incident type occurred at the two tenants. A policy document changed, and the index kept the previous section. In the two cases, the freshness filter fixed all failed cases. But the release gates of v1 did not examine the index.

- Evidence: the [Ledgerloop postmortem](generated/postmortem-ledgerloop-refund-window-drift.md) and the [Parcelpoint postmortem](generated/postmortem-parcelpoint-claims-limit-drift.md).
- Value: the generated roadmap memos give the cost of this cluster for each month. The values are large because each failure is a critical money operation. They are estimates from the tenant cost files.
- Effort: less than one week. The retriever knows the effective date of each section.

### 3. Enforce mode for critical rules

The policy guardrail was in `observe` mode during the incidents. Thus, the wrong refunds and the wrong claim payments occurred, and the monitor only reported them. The intervention `enforce_guardrail` is in the playbook. A tenant must select it for each rule, because a blocked operation also has a cost.

- Evidence: the critical flags in the monitor reports.
- Risk: more escalations. The escalation monitor shows this risk.

### 4. A review queue for silent failures

The monitor cannot see a failure without a signal. With the stand-in model, the monitor saw all failures. A real model will have silent failures. The monitor report gives the number of tickets to review for each window.

- Evidence: the detection quality section of each monitor report.
- Dependency: item 1. Real runs give the real rate of silent failures.

## What we do not build, and why

| item | why not at this time |
|---|---|
| Fine-tuning | The failures in the evidence are failures of knowledge and policy, not of the model weights. |
| A multi-agent system | One agent with good tools and gates is sufficient for the workflows of the two tenants. |
| Kubernetes | Compose and one host are sufficient for the load. The job queue can use more workers. |
| A public demo before item 1 | A public demo with `pipeline-test` numbers can cause readers to think that the results are real. The repository is private at this time. |

## How we measure the roadmap

- Tickets before the first alarm, for each incident.
- The share of the largest clusters with a cause confirmed by intervention.
- The number of silent failures for each 1,000 tickets, after the review queue starts.
- The time to onboard a new tenant in a known domain: configuration files only, no platform code.
