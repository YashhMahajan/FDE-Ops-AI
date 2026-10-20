# 0007: A Production Monitor Without an Oracle

*Language: ASD-STE100. Status: accepted.*

## Context

The evaluation engine compares each trial with an oracle. Production traffic has no oracle. Before this decision, the platform found an incident only with an evaluation run. That is not detection in production.

## Decision

- The monitor uses only signals that a live deployment can see. Examples are guardrail flags, superseded knowledge in the context, escalations, tool errors, latency and tokens.
- Each tenant has `monitors.yaml`. Each monitor has a tolerance, a direction, a severity (`page` or `ticket`) and an explanation.
- A rate monitor uses the Newcombe interval of the change between a reference window and a current window. A value monitor uses a bootstrap interval of the ratio. An alert needs all of the interval to be more than the tolerance.
- A Bernoulli CUSUM in ticket order gives the number of tickets before the alarm.
- In the simulation, the platform knows the oracle. Thus, it measures the precision and the recall of each signal, and the number of silent failures.

## Alternatives

- **Thresholds on point estimates.** They give alarms on noise in small windows.
- **An LLM judge on each production ticket.** It costs a model call for each ticket, and it needs a calibration.

## Results

- In the flagship incident, superseded context gives the first alarm after one ticket. The critical flags come after about 50 tickets.
- The monitor cannot see a failure that has no signal. The report gives a review sample size for these silent failures.
