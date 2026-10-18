"""Run summaries: rates with honest intervals, sliced by scenario and tag, plus a markdown report
whose first line always states where the numbers came from."""

import json
import math
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from fdeops.core.model import FrozenModel
from fdeops.core.provenance import Provenance
from fdeops.eval.runner import RunResult, TrialResult
from fdeops.eval.stats import pass_hat_k, rule_of_three_upper, wilson_interval

PROVENANCE_NOTE = {
    Provenance.PIPELINE_TEST: "produced with a stand-in model to test the pipeline; these numbers "
    "say nothing about any real agent's quality.",
    Provenance.MEASURED_IN_SIMULATION: "measured on the fictional tenant's simulated world; not "
    "real customer outcomes.",
    Provenance.ESTIMATED: "estimated from assumptions; see the assumptions table.",
}


class SliceStat(FrozenModel):
    slice: str
    n: int
    cases: int
    successes: int
    rate: float
    ci_lo: float
    ci_hi: float


class RunSummary(FrozenModel):
    run_id: str
    tenant_id: str
    agent_config_id: str
    agent_config_hash: str
    dataset_ref: str
    dataset_hash: str
    provenance: Provenance
    llm_provider: str
    llm_mode: str
    trials: int
    overall: SliceStat
    pass_hat_k: dict[str, float]
    by_scenario: list[SliceStat]
    by_tag: list[SliceStat]
    evaluator_pass_rates: dict[str, float]
    critical_trials: int
    critical_violations: int
    critical_rate_upper: float
    escalation_confusion: dict[str, int]
    metrics: dict[str, float]


def _slice(name: str, results: Sequence[TrialResult]) -> SliceStat:
    """Success rate with a 95% interval.

    With one trial per case this is a Wilson interval. With several, trials of the same case are
    correlated, so the interval uses the number of *cases* as the effective sample size. That is
    conservative (it treats trials as fully correlated), it never collapses to a zero-width interval
    when every case passes, and it matches how release gates should reason about evidence.
    """
    per_case: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        per_case[r.case_id].append(r.success)
    n = len(results)
    successes = sum(r.success for r in results)
    rate = successes / n if n else 0.0
    cases = len(per_case)
    if all(len(v) == 1 for v in per_case.values()):
        lo, hi = wilson_interval(successes, n)
    else:
        lo, hi = wilson_interval(round(rate * cases), cases) if cases else (0.0, 1.0)
        lo, hi = min(lo, rate), max(hi, rate)
    return SliceStat(
        slice=name, n=n, cases=cases, successes=successes, rate=rate, ci_lo=lo, ci_hi=hi
    )


def _values(results: Sequence[TrialResult], name: str) -> list[float]:
    out: list[float] = []
    for r in results:
        s = r.score(name)
        if s is not None and s.value is not None and not math.isnan(s.value):
            out.append(s.value)
    return out


def summarize(run: RunResult) -> RunSummary:
    results = run.results
    by_scenario: dict[str, list[TrialResult]] = defaultdict(list)
    by_tag: dict[str, list[TrialResult]] = defaultdict(list)
    per_case: dict[str, int] = defaultdict(int)
    for r in results:
        by_scenario[r.scenario].append(r)
        for tag in (*r.tags, f"difficulty:{r.difficulty}"):
            by_tag[tag].append(r)
        per_case[r.case_id] += r.success
    names = sorted({s.name for r in results for s in r.scores if s.passed is not None})
    pass_rates = {}
    for name in names:
        verdicts = [s.passed for r in results if (s := r.score(name)) and s.passed is not None]
        pass_rates[name] = sum(verdicts) / len(verdicts) if verdicts else float("nan")
    critical_trials = sum(any(s.critical for s in r.scores) for r in results)
    violations = sum(
        len([v for v in r.episode.violations if v.severity == "critical"]) for r in results
    )
    n = len(results)
    critical_upper = (
        rule_of_three_upper(n) if critical_trials == 0 else wilson_interval(critical_trials, n)[1]
    )
    cells: dict[str, int] = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for r in results:
        s = r.score("escalation")
        if s is not None:
            cells[s.details["cell"]] += 1
    latency = _values(results, "perf.latency_ms")
    metrics = {
        "retrieval_recall": float(np.mean(_values(results, "retrieval.recall") or [math.nan])),
        "retrieval_mrr": float(np.mean(_values(results, "retrieval.mrr") or [math.nan])),
        "retrieval_ndcg": float(np.mean(_values(results, "retrieval.ndcg") or [math.nan])),
        "stale_hit_rate": float(np.mean(_values(results, "retrieval.stale_hit") or [math.nan])),
        "latency_p50_ms": float(np.percentile(latency, 50)) if latency else math.nan,
        "latency_p95_ms": float(np.percentile(latency, 95)) if latency else math.nan,
        "mean_input_tokens": float(np.mean(_values(results, "perf.input_tokens") or [math.nan])),
        "mean_output_tokens": float(np.mean(_values(results, "perf.output_tokens") or [math.nan])),
        "invalid_tool_calls_per_trial": float(
            np.mean(_values(results, "tool_use.invalid_calls") or [math.nan])
        ),
        "escalation_precision": cells["tp"] / (cells["tp"] + cells["fp"])
        if cells["tp"] + cells["fp"]
        else math.nan,
        "escalation_recall": cells["tp"] / (cells["tp"] + cells["fn"])
        if cells["tp"] + cells["fn"]
        else math.nan,
    }
    return RunSummary(
        run_id=run.run_id,
        tenant_id=run.tenant_id,
        agent_config_id=run.agent_config.id,
        agent_config_hash=run.agent_config_hash,
        dataset_ref=run.dataset_ref,
        dataset_hash=run.dataset_hash,
        provenance=run.provenance,
        llm_provider=run.llm_provider,
        llm_mode=run.llm_mode,
        trials=run.trials,
        overall=_slice("overall", results),
        pass_hat_k={
            str(k): pass_hat_k(list(per_case.values()), run.trials, k)
            for k in range(1, run.trials + 1)
        },
        by_scenario=[_slice(k, v) for k, v in sorted(by_scenario.items())],
        by_tag=[_slice(k, v) for k, v in sorted(by_tag.items())],
        evaluator_pass_rates=pass_rates,
        critical_trials=critical_trials,
        critical_violations=violations,
        critical_rate_upper=critical_upper,
        escalation_confusion=cells,
        metrics=metrics,
    )


def _pct(x: float) -> str:
    return "n/a" if math.isnan(x) else f"{x:.1%}"


def _table(rows: Sequence[SliceStat]) -> list[str]:
    out = ["| slice | trials | success | 95% CI |", "|---|---:|---:|---|"]
    out += [
        f"| {r.slice} | {r.n} | {_pct(r.rate)} | {_pct(r.ci_lo)} – {_pct(r.ci_hi)} |" for r in rows
    ]
    return out


def render_markdown(s: RunSummary) -> str:
    lines = [
        f"> **Provenance: {s.provenance.value}**: {PROVENANCE_NOTE[s.provenance]}",
        "",
        f"# Evaluation run `{s.run_id}`",
        "",
        f"- Tenant: `{s.tenant_id}` · Agent config: `{s.agent_config_id}` "
        f"(`{s.agent_config_hash[:19]}`)",
        f"- Dataset: `{s.dataset_ref}` (`{s.dataset_hash[:19]}`) · Trials per case: {s.trials}",
        f"- Model: `{s.llm_provider}` · LLM mode: `{s.llm_mode}`",
        "",
        "## Task success",
        "",
        f"**{_pct(s.overall.rate)}** of {s.overall.n} trials "
        f"(95% CI {_pct(s.overall.ci_lo)} – {_pct(s.overall.ci_hi)}, {s.overall.cases} cases).",
        "",
        "Reliability (pass^k: all k trials of a case succeed): "
        + ", ".join(f"k={k}: {_pct(v)}" for k, v in s.pass_hat_k.items()),
        "",
        f"Critical violations: {s.critical_violations} in {s.critical_trials} trials "
        f"(upper 95% bound on the critical-trial rate: {_pct(s.critical_rate_upper)}).",
        "",
        "## By scenario",
        "",
        *_table(s.by_scenario),
        "",
        "## By tag",
        "",
        *_table(s.by_tag),
        "",
        "## Evaluator pass rates",
        "",
        "| evaluator | pass rate |",
        "|---|---:|",
        *[f"| {k} | {_pct(v)} |" for k, v in s.evaluator_pass_rates.items()],
        "",
        "## Metrics",
        "",
        "| metric | value |",
        "|---|---:|",
        *[f"| {k} | {'n/a' if math.isnan(v) else f'{v:,.3f}'} |" for k, v in s.metrics.items()],
        "",
        f"Escalation confusion: {s.escalation_confusion}",
        "",
    ]
    return "\n".join(lines)


def save_run(run: RunResult, root: Path) -> Path:
    out = root / run.run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "run.json").write_text(run.model_dump_json(), encoding="utf-8")
    summary = summarize(run)
    (out / "summary.json").write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    (out / "report.md").write_text(render_markdown(summary), encoding="utf-8")
    return out


def load_run(path: Path) -> RunResult:
    return RunResult.model_validate(json.loads((path / "run.json").read_text(encoding="utf-8")))
