# 0005: Release Gates on Confidence Limits

*Language: ASD-STE100. Status: accepted.*

## Context

A point estimate on a small dataset is not a good release decision. For example, 69 of 69 correct cases give a lower 95% limit of 94.7%, not 100%. A team that changes thresholds until a release passes gets no protection from the gates.

## Decision

- Each gate uses a confidence limit. Examples are the lower limit of task success and the rule-of-three limit of critical violations.
- Important slices have a non-inferiority margin.
- Each gate has an explanation (`why`) in `gates.yaml`. A gate without an explanation does not load.
- A gate that the platform cannot measure fails, unless the tenant file accepts this.
- The gates of each tenant are different, because the risk tolerance is different.

## Alternatives

- **Point estimates.** They pass releases that the data does not support.
- **One set of gates for all tenants.** A wrong refund and a late parcel do not have the same risk.

## Results

- Small datasets cannot pass strict gates. This shows the need for more cases. It is not a defect.
- Each release decision has a memo with each gate, its value and its explanation.
