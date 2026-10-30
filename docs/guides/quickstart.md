# Quickstart: Use FDE-Ops-AI on Your Own Workflow

You need about 15 minutes for this guide. You do not need a GPU, Docker or an API key.

## What you will do

1. Check your machine.
2. Make a tenant for your company.
3. Test an agent against it.
4. Read the report and find the failures.

## Step 1: Install and check

You must have Python 3.11 (or a subsequent version) and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run fdeops doctor
```

The `doctor` command shows each problem on one line. A line with `fail` stops you. A line with `warn` is optional.

## Step 2: Make a tenant

A tenant is the folder that has the data of one customer: policy, knowledge base, gates and monitors. The command copies a starter from a domain pack. Use `billing` for payment and refund work. Use `logistics` for shipping and claims work.

```bash
uv run fdeops init tenants/<your-tenant> --pack billing --name "<Your Company>"
uv run fdeops tenant validate tenants/<your-tenant>
```

Then change two items:

- `policy.yaml` has the business rules. The oracle uses these rules to select if an agent is correct.
- `kb/` has the knowledge-base sections that the agent reads. Add a new version of a file as `name.v2.md` with a new `effective_from` date. The platform records which version is current.

The world data (customers, invoices, shipments) is simulated. Put no real customer data in the tenant folder.

## Step 3: Build the datasets and test an agent

```bash
uv run fdeops dataset build --tenant tenants/<your-tenant>
```

The command makes a development split (51 cases) and a test split (69 cases), with the correct answer for each case. The starter tenant has 12 scenarios. Run the example agent on the development split:

```bash
uv run fdeops run --tenant tenants/<your-tenant> --agent configs/agents/<your-tenant>-heuristic.yaml --dataset data/datasets/<your-tenant>/support-core@v1 --split dev --external examples/agents/careful_refunder.py:agent
```

## Step 4: Read the result

The command prints the success rate with its 95% confidence interval, and the number of critical violations. It writes `report.md` in the run folder.

The example agent in step 3 gives these numbers on the dev split of a tenant that you make with the `billing` pack (51 cases):

```
[measured-in-simulation] run_...: success 78.4% (95% CI 65.4%-87.5%, n=51), critical trials 0
```

A naive agent that refunds each invoice gives 21.6% (95% CI 12.5%-34.6%) and 33 critical trials in the same 51 cases. Refer to [test your own agent](test-your-own-agent.md) for the full table.

To see the effect of a change, run two agents on the same split and compare them. The comparison pairs the results case by case, so you can see a small difference.

```bash
uv run fdeops compare <run-a> <run-b>
```

## What to do next

- Write your own agent. Refer to [test your own agent](test-your-own-agent.md).
- Use a real model. Refer to [real model runs](real-model-runs.md).
- Find the cause of failures with `fdeops diagnose`.
- Release a fix with gates. Refer to the [runbook](../operations/runbook.md).
