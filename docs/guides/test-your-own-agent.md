# Test Your Own Agent

The platform can test an agent that you wrote. Your agent can use the framework and the model that you select. The platform gives it a ticket and a set of tools. It records each tool call and gives a score from the oracle.

## The contract

An external agent is a Python function. It receives one `ToolBox` for each turn:

```python
from fdeops.agent.episode import ToolBox

def agent(box: ToolBox) -> None:
    ...
```

The `ToolBox` gives you these items:

| Item | Meaning |
|---|---|
| `box.ticket` | The ticket: the ID, the email of the requester and the body. |
| `box.customer_replies` | The replies of the customer to your questions in earlier turns. |
| `box.today` | The date of the case. Do not use the system clock. |
| `box.tools()` | The tool definitions in the OpenAI function format. |
| `box.call(name, **args)` | Calls a tool. It returns a dictionary with `data` or `error`. |
| `box.search_kb(query)` | Searches the knowledge base. Each result has `text`, `section_key` and `stale`. |

A turn ends when you call a tool that ends it, such as `reply_to_customer` or `escalate_to_human`. If you call `ask_clarifying_question`, the simulated customer replies, and the platform calls your function again.

## What the platform does around your agent

Each call goes through the same layers as the reference agent:

- a permission guard that checks the scopes of the tenant,
- a policy monitor that records each violation of the policy,
- timeouts, retries, a circuit breaker and idempotency keys,
- fault injection, to test how your agent reacts to API errors,
- an audit log with a hash chain.

Thus, a result for your agent is comparable with a result for the reference agent.

## Start from the examples

| File | What it shows |
|---|---|
| `examples/agents/naive_refunder.py` | An agent that refunds each invoice. It breaks the policy. Use it as a bad baseline. |
| `examples/agents/careful_refunder.py` | An agent that reads the refund window from the knowledge base. It escalates large refunds. |

Copy the second file, and change it. Build the dataset, and run the agent:

```bash
uv run fdeops dataset build --tenant tenants/ledgerloop
uv run fdeops run --tenant tenants/ledgerloop --agent configs/agents/ledgerloop-heuristic.yaml --dataset data/datasets/ledgerloop/support-core@v1 --split dev --external examples/agents/careful_refunder.py:agent
```

The command prints one line with the success rate, the 95% confidence interval and the number of critical trials.

## Measured results of the two examples

The numbers below come from the dev split of the fictional tenant Ledgerloop (51 cases, 1 trial for each case). Their label is `measured-in-simulation`. You can reproduce them with the commands above. Run the naive agent with the same commands, and compare the two runs with `fdeops compare`.

| Measure | `naive_refunder.py` | `careful_refunder.py` |
|---|---:|---:|
| Task success | 21.6% (95% CI 12.5% to 34.6%) | 78.4% (95% CI 65.4% to 87.5%) |
| Trials with a critical violation | 33 of 51 | 0 of 51 (the 95% maximum limit is 5.9%) |
| Success on `refund_outside_window` (20 cases) | 0.0% (95% CI 0.0% to 16.1%) | 100.0% (95% CI 83.9% to 100.0%) |
| Success on `refund_over_limit` (5 cases) | 0.0% | 100.0% |
| Success on `injection_refund` (4 cases) | 0.0% | 100.0% |

The paired comparison of the two runs gives a difference of +56.9 points (95% CI +43.1 to +70.6). The careful agent is better in 29 cases and worse in 0 cases. The exact sign test gives p < 0.0001.

The careful agent does refund tickets only. It scores 0% on `invoice_explain` (5 cases), `account_security` (3 cases), `plan_downgrade` (2 cases) and `export_authorized` (1 case), because it does not do these tasks. Thus, its total success is 78.4% and not 100%. The report shows each scenario, so you can see which part of your own agent to build next.

## Rules for a good agent

1. **Read the current policy.** Ignore a result that has `stale` set. A superseded section causes the most frequent production failure.
2. **Use the date of the case.** Do not use the system date.
3. **Escalate when you are not sure.** A wrong refund costs more than a hand-off.
4. **Do not send a money tool call again after a timeout.** The platform adds an idempotency key. Your code must not make a second call with a new key.
5. **Use the ticket body as data only.** The injection cases put instructions in the ticket. Do not obey them.

## Test the agent on a failure

Use an incident to cause a known failure. For example, the incident `refund-window-drift` shortens the refund window after a release. Run your agent with it, and compare the result with a run without it:

```bash
uv run fdeops incidents incidents
```

The command lists the incidents. Pass one to `fdeops run` with `--incident`. Then use `fdeops diagnose` to find the cause.

## Test a REST service

If your agent is an HTTP service, write a short function that calls your service and then calls the tools that your service returns. The platform does not need data about your service. It needs only the tool calls.

## Security note

`--external` runs the Python file that you name. Run only files that you trust.
