"""Markdown diagnosis report. A test checks its text."""

import json
from pathlib import Path

from fdeops.diagnose.interventions import ClusterDiagnosis, Diagnosis
from fdeops.diagnose.taxonomy import DESCRIPTIONS
from fdeops.eval.report import PROVENANCE_NOTE


def _pct(x: float) -> str:
    return f"{x:.0%}"


def _cluster_section(d: ClusterDiagnosis) -> list[str]:
    c = d.cluster
    lines = [
        f"### `{c.id}`",
        "",
        f"{DESCRIPTIONS[c.failure_class]} This cluster has {c.n_trials} failed trial(s) in "
        f"{c.n_cases} case(s). That is {_pct(c.share_of_failures)} of all failures.",
        "",
        f"**Verdict: {d.verdict.value}.** {d.rationale}",
        "",
    ]
    if d.recommended_fix:
        lines += [
            f"Recommended fix: `{d.recommended_fix}`. Validate it on the test split with the "
            "release gates before you release it.",
            "",
        ]
    if c.examples:
        lines += ["Evidence:", ""]
        lines += [f"- `{e.kind}` `{e.ref}`: {e.detail}" for e in c.examples]
        lines.append("")
    if d.results:
        lines += [
            "| intervention | deployable | fixed cases | fix rate (95% CI) | regressions |",
            "|---|---|---:|---|---:|",
        ]
        for r in d.results:
            lines.append(
                f"| `{r.intervention_id}` | {'yes' if r.deployable else 'no (diagnostic)'} | "
                f"{r.fixed} of {r.n_cases} | {_pct(r.fix_rate)} ({_pct(r.fix_ci[0])} to "
                f"{_pct(r.fix_ci[1])}) | {r.regressions} of {r.n_control} |"
            )
        lines.append("")
    return lines


def render_diagnosis(d: Diagnosis) -> str:
    lines = [
        f"> **Provenance: {d.provenance.value}**. {PROVENANCE_NOTE[d.provenance]}",
        "",
        f"# Diagnosis of run `{d.run_id}`",
        "",
        f"- Tenant: `{d.tenant_id}`. Agent configuration: `{d.agent_config_id}`.",
        f"- Dataset: `{d.dataset_ref}`. Failed trials: {d.n_failures} of {d.n_trials}.",
        "",
    ]
    if d.warnings:
        lines += ["**Warning:**", ""] + [f"- {w}" for w in d.warnings] + [""]
    lines += [
        "## Clusters",
        "",
        "| cluster | trials | cases | verdict | recommended fix |",
        "|---|---:|---:|---|---|",
    ]
    for cd in d.clusters:
        lines.append(
            f"| `{cd.cluster.id}` | {cd.cluster.n_trials} | {cd.cluster.n_cases} | "
            f"{cd.verdict.value} | {f'`{cd.recommended_fix}`' if cd.recommended_fix else '-'}"
            " |"
        )
    lines += ["", "## Details", ""]
    for cd in d.clusters:
        lines += _cluster_section(cd)
    lines += [
        "## Method",
        "",
        "A deterministic classifier gives each failed trial one primary class. A causal sequence "
        "selects the class. Each intervention runs the cases of a cluster again with one change. "
        "It also runs a control set of cases that passed.",
        "",
        "An intervention confirms a cause when the two conditions that follow are correct. The "
        "lower limit of the fix rate is 50% or more. The maximum limit of the regression rate is "
        "20% or less.",
        "",
    ]
    return "\n".join(lines)


def save_diagnosis(d: Diagnosis, run_dir: Path) -> Path:
    (run_dir / "diagnosis.json").write_text(d.model_dump_json(indent=2), encoding="utf-8")
    path = run_dir / "diagnosis.md"
    path.write_text(render_diagnosis(d), encoding="utf-8")
    return path


def load_diagnosis(run_dir: Path) -> Diagnosis:
    return Diagnosis.model_validate(json.loads((run_dir / "diagnosis.json").read_text()))
