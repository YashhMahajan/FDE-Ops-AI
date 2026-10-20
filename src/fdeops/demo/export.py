"""Export a demo as static JSON files for the web UI. The UI needs no backend and no model."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fdeops import __version__
from fdeops.demo.flagship import DemoResult
from fdeops.diagnose.classify import classify
from fdeops.eval.report import render_markdown, summarize
from fdeops.eval.runner import RunResult
from fdeops.release.memo import render_memo

DETAIL_RUNS = ("v1_test", "monitor_test", "monitor_dev", "v2_test")


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, default=str, separators=(",", ":")), encoding="utf-8")


def _trials(run: RunResult, knowledge: dict[str, tuple[str, ...]]) -> list[dict[str, Any]]:
    out = []
    for r in run.results:
        label = classify(r, knowledge)
        outcome = r.score("outcome")
        out.append(
            {
                "case_id": r.case_id,
                "trial": r.trial,
                "scenario": r.scenario,
                "tags": list(r.tags),
                "difficulty": r.difficulty,
                "success": r.success,
                "primary_failure": label.primary.value if label else None,
                "resolution": outcome.details.get("derived_resolution") if outcome else None,
                "steps": r.episode.steps,
                "latency_ms": r.episode.llm_latency_ms + r.episode.tool_latency_ms,
                "violations": [v.rule for v in r.episode.violations],
            }
        )
    return out


def export_demo(res: DemoResult, out: Path) -> Path:
    t = res.tenant
    knowledge = t.pack.knowledge_rules
    runs_index = []
    for label, run in res.runs.items():
        s = summarize(run)
        runs_index.append(
            {
                "label": label,
                "run_id": run.run_id,
                "config": run.agent_config.id,
                "split": run.dataset_split,
                "provenance": run.provenance.value,
                "incident": run.incident.id if run.incident else None,
                "success": s.overall.rate,
                "ci": [s.overall.ci_lo, s.overall.ci_hi],
                "critical_trials": s.critical_trials,
                "n": s.overall.n,
            }
        )
        _write(
            out / "runs" / f"{run.run_id}.json",
            {
                "label": label,
                "summary": s.model_dump(mode="json"),
                "report_md": render_markdown(s),
                "trials": _trials(run, knowledge),
            },
        )
        if label in DETAIL_RUNS:
            for r in run.results:
                _write(
                    out / "trials" / run.run_id / f"{r.case_id}-{r.trial}.json",
                    r.model_dump(mode="json"),
                )
    for name, cmp in res.comparisons.items():
        _write(out / "compare" / f"{name}.json", cmp.model_dump(mode="json"))
    if res.diagnosis is not None:
        _write(out / "diagnosis.json", res.diagnosis.model_dump(mode="json"))
    if res.registry is not None:
        reg = res.registry
        prod = reg.production()
        _write(
            out / "releases.json",
            {
                "production": prod.model_dump(mode="json") if prod else None,
                "decisions": [
                    {**d.model_dump(mode="json"), "memo_md": render_memo(d)}
                    for d in reg.decisions()
                ],
                "history": [e.model_dump(mode="json") for e in reg.history()],
                "regression_cases": reg.regression_cases(),
            },
        )
    if res.roi is not None:
        _write(
            out / "impact.json",
            {**res.roi.model_dump(mode="json"), "report_md": res.reports.get("impact", "")},
        )
    _write(
        out / "opportunities.json",
        {
            "opportunities": [o.model_dump() for o in res.opportunities],
            "roadmap_md": res.reports.get("roadmap", ""),
        },
    )
    q = t.data_quality
    provenance = sorted({r.provenance.value for r in res.runs.values()})
    _write(
        out / "index.json",
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "fdeops_version": __version__,
            "provenance": provenance,
            "tenant": {
                "id": t.id,
                "display_name": t.config.display_name,
                "pack": t.pack.id,
                "notes": t.config.notes,
                "scenarios": sorted(t.pack.scenarios()),
                "kb_sections": len(t.kb.keys()),
                "pii_redaction": t.config.pii.redact,
                "data_quality": {
                    "loaded": sum(q.loaded.values()),
                    "isolated": sum(q.quarantined.values()),
                    "issues": len(q.issues),
                },
            },
            "steps": [s.model_dump() for s in res.steps],
            "runs": runs_index,
            "detail_runs": [res.runs[k].run_id for k in DETAIL_RUNS if k in res.runs],
            "comparisons": list(res.comparisons),
        },
    )
    return out
