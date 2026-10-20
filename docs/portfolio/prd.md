# Product Requirements: FDE-Ops-AI

*Language: ASD-STE100. Refer to the [glossary](../glossary.md). Status: approved for version 2.0. The tenants and their data are fictional.*

## 1. Problem

Companies put AI agents into support, billing and logistics workflows. After the first release, three problems occur:

1. **Nobody sees the failures.** Production traffic has no correct answers. An agent can give wrong refunds for hours before a person sees a pattern.
2. **Causes are guesses.** A team sees a decrease in quality and changes the prompt. Nobody proves that the change fixed the cause.
3. **Releases are opinions.** A demo on ten good tickets becomes a release decision. Nobody can tell if the new version is better, or only different.

Each customer has different policies, data and risk tolerance. Thus, a forward deployed engineer (FDE) does this work again for each customer.

## 2. Users

| user | task | what the user needs from the product |
|---|---|---|
| Forward deployed engineer | Connects the agent to the systems of a customer | Connectors that operate with bad APIs and bad data, tenant settings in files, an onboarding that needs no platform code |
| AI engineer | Makes the agent better | Reproducible evaluations, traces, a diagnosis with proof, comparisons with intervals |
| Release owner (approver) | Selects the version that goes to production | Gates with explanations, a decision memo, a rollback |
| Product manager | Selects what the team builds next | Failures as ranked opportunities with costs, ROI with uncertainty |
| Support manager of the customer | Operates the support team | Alerts with a severity, a review sample for silent failures |

## 3. Goals and measures of success

| goal | measure | target for version 2.0 | result |
|---|---|---|---|
| Find failures in production fast | Tickets before the first alarm, without an oracle | Less than one hour of traffic | 1 ticket (Ledgerloop), 8 tickets (Parcelpoint) |
| Prove causes | Share of cluster causes confirmed by intervention | The largest cluster of each flagship incident | Confirmed for the two tenants |
| Make release decisions with evidence | Gates that use confidence limits | All gates of each tenant | 8 gates for each tenant, no point estimates |
| Onboard a new tenant without platform code | Platform files that name a tenant | 0 | 0 (a test examines it) |
| Show business value honestly | ROI as a distribution against two baselines | 5th, 50th and 95th percentiles | Yes, with labels for measured values and assumptions |

The results come from the [benchmark report](generated/benchmark-report.md) and the [case study](generated/case-study-parcelpoint.md). The current model is a stand-in. Real model results come in milestone M11.

## 4. Requirements

### 4.1 Deployment

- R1. A tenant is a folder of files: policy, knowledge base, gates, monitors, costs and effort. No tenant code is in the platform.
- R2. Each tool call goes through a permission guard, a policy monitor, retries with backoff, a circuit breaker, a rate limit and a timeout.
- R3. An operation that changes data occurs one time only, also after a retry. An idempotency key controls this.
- R4. Each tool call has an audit record in a hash chain.
- R5. External agents use the same connectors and the same evaluators as the reference agent.

### 4.2 Evaluation

- R6. An oracle calculates the correct result from the policy and the data. An LLM does not write the correct answers.
- R7. Each rate has a 95% interval. Comparisons are paired at case level.
- R8. An LLM judge is part of a gate only after a calibration against human labels.
- R9. The dev split selects fixes. The test split validates them. A guard stops the use of the test split for diagnosis.

### 4.3 Detection

- R10. The production monitor uses only signals that a live deployment can see.
- R11. An alert occurs only when all of the 95% interval of the change is more than the tolerance.
- R12. Each monitor has a severity and an explanation in the tenant file.
- R13. In the simulation, the platform measures how many failures the monitor sees, and how many failures are silent.

### 4.4 Diagnosis and improvement

- R14. Each failed trial gets one primary class from a fixed taxonomy.
- R15. A cause is "confirmed" only when an intervention fixes the cluster and does not break control cases.
- R16. The improvement loop stops before production. A person with the approver role makes the decision.

### 4.5 Release

- R17. A release is a frozen bundle with a hash: model, prompt, retrieval, tools, knowledge base, dataset and gates.
- R18. A gate that the platform cannot measure fails, unless the tenant file accepts it.
- R19. An approval adds the incident cases to the regression suite. A rollback is one command.

### 4.6 Business value

- R20. Each assumption has a low value, a likely value, a high value and a source.
- R21. ROI uses a Monte Carlo simulation. The report gives percentiles and the probability that the savings are more than zero.
- R22. One baseline is a person only. The other baseline is a FAQ responder without an LLM.

## 5. Constraints

- No paid model APIs. The platform uses free models on OpenRouter, or open models with vLLM on a free GPU.
- Each model call can go into a cassette. A replay costs nothing and gives the same result.
- The author does not run services on a laptop. CI runs Postgres, Compose and the browser screenshots.
- All documents use ASD-STE100. CI examines them.

## 6. Out of scope

- Model training or fine-tuning.
- Changes to production without a person.
- Real customer data.
- Kubernetes, or a general framework for agents.

## 7. Risks

| risk | effect | mitigation |
|---|---|---|
| The simulation is easier than real traffic | Results look better than they are | Provenance labels on each report. Real model runs in M11. Adversarial scenarios. |
| A free model changes or stops | Recordings do not replay | Cassettes keep each response. The model name is part of the cassette key. |
| Monitors give too many alerts | The team stops to read them | Interval tests, tolerances in the tenant file, a CUSUM level for each tenant |
| Silent failures | The monitor cannot see them | The report gives a review sample size for tickets without a flag |
