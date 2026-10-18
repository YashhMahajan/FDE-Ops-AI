# FDE-Ops-AI

**Deploy AI agents into real business workflows, then prove with evidence whether they are ready to ship.**

FDE-Ops-AI evaluates, observes, diagnoses, and improves AI agents running inside customer workflows. It also makes release and ROI decisions with honest uncertainty. The first workflow is a customer-support agent for B2B SaaS. It is exercised against a deterministic simulated customer world whose ground truth comes from a policy oracle. No LLM writes the answer key.

> Status: early development. See the [design](docs/design/2026-10-18-fde-ops-ai-design.md) and the [current plan](docs/plans/2026-10-18-m0-m3-foundations-to-eval.md).

## Quick start (development)

```bash
uv sync
make check        # lint, types, layering contract, tests
```

All companies, people, and data in this repository are **fictional**.
