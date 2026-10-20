"""Portfolio documents that the platform writes from its own records.

The postmortem, the benchmark report and the deployment case study use only values from demo runs
and from the tenant files. Thus, each number in them has a source. A test checks their text.
"""

from collections.abc import Sequence
from pathlib import Path

from fdeops.core.provenance import Provenance
from fdeops.demo.flagship import DemoResult
from fdeops.eval.report import PROVENANCE_NOTE, summarize
from fdeops.impact.costs import load_costs
from fdeops.monitor.config import load_monitors
from fdeops.monitor.detect import MonitorReport
from fdeops.release.models import load_gates

RUN_NAMES = {
    "v1_test": "v1 before the incident",
    "monitor_test": "v1 during the incident",
    "monitor_dev": "v1 during the incident (dev split)",
    "v2_test": "v2 with the fix",
    "faq_test": "FAQ baseline, no LLM",
}


def _provenance(results: Sequence[DemoResult]) -> Provenance:
    values = {r.provenance for d in results for r in d.runs.values()}
    if Provenance.PIPELINE_TEST in values:
        return Provenance.PIPELINE_TEST
    return Provenance.MEASURED_IN_SIMULATION


def _head(results: Sequence[DemoResult]) -> list[str]:
    p = _provenance(results)
    return [f"> **Provenance: {p.value}**. {PROVENANCE_NOTE[p]}", ""]


def _tickets_per_hour(res: DemoResult) -> float:
    c = load_costs(res.tenant.root / "costs.yaml")
    return c.monthly_ticket_volume.likely * c.adoption_rate.likely / (30 * 24)


def _duration(tickets: int, per_hour: float) -> str:
    minutes = tickets / per_hour * 60
    if minutes < 90:
        return f"about {max(1, round(minutes))} minutes"
    return f"about {minutes / 60:.1f} hours"


def _first_alarm(m: MonitorReport) -> tuple[str, int] | None:
    hits = [(a.signal, a.detected_after) for a in m.alerts if a.detected_after]
    return min(hits, key=lambda x: x[1]) if hits else None


def render_postmortem(res: DemoResult) -> str:
    """A postmortem of the flagship incident, from the records of the demo."""
    t = res.tenant
    during = res.monitors["during_incident"]
    cmp = res.comparisons["v1_vs_monitor"]
    d = res.diagnosis
    top = d.clusters[0] if d and d.clusters else None
    imp = res.improvement
    incident = res.runs["monitor_test"].incident
    per_hour = _tickets_per_hour(res)
    worst = min(cmp.by_scenario.items(), key=lambda kv: kv[1].mean)
    critical = summarize(res.runs["monitor_test"]).critical_trials
    first = _first_alarm(during)
    opp = next((o for o in res.opportunities if o.cluster_id == (top and top.cluster.id)), None)
    lines = [
        *_head([res]),
        f"# Postmortem: `{incident.id if incident else 'incident'}` at {t.config.display_name}",
        "",
        "*The platform wrote this document from the records of the "
        "flagship demo. The tenant and its data are fictional.*",
        "",
        "## Summary",
        "",
        f"{incident.description if incident else ''} The support agent v1 used the superseded "
        f"text, and task success decreased by {-cmp.diff.mean * 100:.1f} points. The production "
        "monitor gave an alert before the evaluation measured the regression. A counterfactual "
        "replay confirmed the cause. A fix went through the release gates, and a person "
        "approved it.",
        "",
        "## Impact",
        "",
        f"- Task success on the test split changed by {cmp.diff.mean:+.3f} (95% CI "
        f"{cmp.diff.lo:+.3f} to {cmp.diff.hi:+.3f}).",
        f"- The largest change was in `{worst[0]}` ({worst[1].mean:+.3f}).",
        f"- Trials with a critical violation: {critical}. Each is a wrong money operation or a "
        "wrong data operation.",
    ]
    if opp:
        lines.append(
            f"- Estimated cost if the problem continues: about ${opp.cost_per_month:,.0f} each "
            f"month ({opp.affected_tickets_per_month:,.0f} tickets each month). This value uses "
            "the assumptions in `costs.yaml`."
        )
    lines += [
        "",
        "## Detection",
        "",
        "The monitor uses only signals that a live deployment can see. It does not use the "
        f"oracle. At the likely traffic of {per_hour:.1f} tickets each hour, these are the "
        "alarms:",
        "",
        "| signal | severity | reference | during the incident | alarm after | time |",
        "|---|---|---:|---:|---:|---|",
    ]
    for a in sorted(during.alerts, key=lambda a: a.detected_after or 10**9):
        n = a.detected_after
        lines.append(
            f"| `{a.signal}` | {a.severity} | {a.reference:.1%} | {a.current:.1%} | "
            f"{n if n else 'n/a'} ticket(s) | {_duration(n, per_hour) if n else 'n/a'} |"
        )
    q = during.quality
    lines += [
        "",
        f"The monitor saw {q.seen} of {q.failures} failed trials. {q.silent} failure(s) had no "
        "flag.",
        "",
        "## Timeline",
        "",
        "| step | event | evidence |",
        "|---|---|---|",
        "| 0 | The policy document changes. The index keeps the previous section. | incident "
        f"`{incident.id if incident else ''}` |",
    ]
    if first:
        lines.append(
            f"| 1 | First alarm: `{first[0]}` after {first[1]} ticket(s) "
            f"({_duration(first[1], per_hour)}). | run `{during.current_run}` |"
        )
    lines += [
        f"| 2 | The evaluation measures the regression ({cmp.diff.mean:+.3f}). | runs "
        f"`{cmp.a_run_id}` and `{cmp.b_run_id}` |",
    ]
    if top:
        lines.append(
            f"| 3 | Diagnosis: `{top.cluster.id}`, {top.verdict.value}. | run "
            f"`{res.runs['monitor_dev'].run_id}` |"
        )
    if imp:
        lines.append(
            f"| 4 | The improvement loop proposes `{imp.intervention_id}` and stops at "
            f"`{imp.status}`. | proposal `{imp.proposal_id}` |"
        )
        if imp.decision_id:
            lines.append(
                "| 5 | A person with the approver role approves v2. | decision "
                f"`{imp.decision_id}` |"
            )
    after = res.monitors.get("after_fix")
    if after:
        lines.append(
            f"| 6 | The monitor gives {len(after.alerts)} alert(s) for v2. | run "
            f"`{after.current_run}` |"
        )
    lines += ["", "## Root cause", ""]
    if top:
        seen: set[tuple[str, str]] = set()
        evidence = []
        for e in top.cluster.examples:
            if (e.kind, e.ref) not in seen:
                seen.add((e.kind, e.ref))
                evidence.append(f"- `{e.kind}` `{e.ref}`: {e.detail}")
        lines += [
            f"**{top.verdict.value}.** {top.rationale}",
            "",
            "Evidence:",
            "",
            *evidence,
            "",
            "| intervention | fixed cases | regressions in control cases |",
            "|---|---:|---:|",
            *[
                f"| `{r.intervention_id}` | {r.fixed} of {r.n_cases} | {r.regressions} of "
                f"{r.n_control} |"
                for r in top.results
            ],
        ]
    lines += ["", "## Resolution", ""]
    if imp and imp.intervention_id:
        dev = imp.dev_experiment or {}
        lines.append(
            f"The fix is `{imp.intervention_id}`. On the dev split, success changed by "
            f"{dev.get('diff_mean', 0.0):+.3f}. The test split was used only for the release "
            "gates."
        )
    if "monitor_vs_v2" in res.comparisons:
        c2 = res.comparisons["monitor_vs_v2"]
        lines.append(
            f"Against v1 during the incident, v2 changed success by {c2.diff.mean:+.3f} (95% CI "
            f"{c2.diff.lo:+.3f} to {c2.diff.hi:+.3f})."
        )
    reg = res.registry
    decision = reg.decision(imp.decision_id) if reg and imp and imp.decision_id else None
    if decision:
        passed = sum(g.passed for g in decision.gates)
        lines += [
            "",
            f"v2 passed {passed} of {len(decision.gates)} gates. The approval added "
            f"{len(decision.regression_cases)} incident cases to the regression suite.",
        ]
    lines += [
        "",
        "## What occurred correctly",
        "",
        "- The monitor found the drift from the context of the agent, before the critical flags.",
        "- The diagnosis tested the cause with an intervention. It did not use a correlation only.",
        "- The improvement loop stopped before production. A person made the release decision.",
        "",
        "## What we must make better",
        "",
        "- The release gates of v1 did not examine the index for superseded sections.",
        "- The policy guardrail was in `observe` mode. Thus, wrong operations occurred before the "
        "fix.",
        "",
        "## Tasks",
        "",
        "| task | owner | evidence |",
        "|---|---|---|",
        "| Add the incident cases to the regression suite | release owner | the approval of v2 |",
        "| Add a check of the index for superseded sections to the release gates | platform "
        "team | the root cause |",
        "| Set the policy guardrail to enforce mode for critical rules | tenant owner | the "
        "critical flags |",
    ]
    if q.review_sample:
        lines.append(
            f"| Review {q.review_sample} tickets without a flag each week | support manager | "
            "silent failures |"
        )
    lines.append("")
    return "\n".join(lines)


def render_benchmark(results: Sequence[DemoResult]) -> str:
    """The benchmark report: each run of each tenant, with intervals, gates and monitors."""
    lines = [
        *_head(results),
        "# Benchmark Report",
        "",
        "*The platform wrote this document from the records of the flagship demo for each tenant.*",
        "",
        "## Setup",
        "",
        "| tenant | dataset | test cases | dev cases | model | trials |",
        "|---|---|---:|---:|---|---:|",
    ]
    for d in results:
        v1 = d.runs["v1_test"]
        s = summarize(v1)
        dev = d.runs["monitor_dev"]
        lines.append(
            f"| {d.tenant.config.display_name} | `{v1.dataset_ref}` | {s.overall.cases} | "
            f"{summarize(dev).overall.cases} | `{v1.llm_provider}` | {v1.trials} |"
        )
    lines += [
        "",
        "Each interval is a 95% interval. With more than one trial for each case, the interval "
        "uses the number of cases as the sample size.",
        "",
        "## Task success",
        "",
        "| tenant | run | success | 95% CI | critical trials | p95 latency (ms) | tokens |",
        "|---|---|---:|---|---:|---:|---:|",
    ]
    for d in results:
        for label, run in d.runs.items():
            if label == "monitor_dev":
                continue
            s = summarize(run)
            m = s.metrics
            tokens = m.get("mean_input_tokens", 0.0) + m.get("mean_output_tokens", 0.0)
            lines.append(
                f"| {d.tenant.id} | {RUN_NAMES.get(label, label)} | {s.overall.rate:.1%} | "
                f"{s.overall.ci_lo:.1%} to {s.overall.ci_hi:.1%} | {s.critical_trials} | "
                f"{m.get('latency_p95_ms', 0.0):,.0f} | {tokens:,.0f} |"
            )
    lines += ["", "## Paired comparisons", ""]
    lines += [
        "| tenant | comparison | change | 95% CI | p (sign test) |",
        "|---|---|---:|---|---:|",
    ]
    names = {"v1_vs_monitor": "v1, then the incident", "monitor_vs_v2": "the incident, then v2"}
    for d in results:
        for key, c in d.comparisons.items():
            lines.append(
                f"| {d.tenant.id} | {names.get(key, key)} | {c.diff.mean:+.3f} | "
                f"{c.diff.lo:+.3f} to {c.diff.hi:+.3f} | {c.mcnemar_p:.4f} |"
            )
    lines += ["", "## Release gates", ""]
    lines += ["| tenant | release | gates passed | status |", "|---|---|---:|---|"]
    for d in results:
        if d.registry is None:
            continue
        for dec in d.registry.decisions():
            passed = sum(g.passed for g in dec.gates)
            lines.append(
                f"| {d.tenant.id} | {dec.release.version} | {passed} of {len(dec.gates)} | "
                f"{dec.status} |"
            )
    lines += ["", "## Production monitor", ""]
    lines += [
        "| tenant | window | alerts | first alarm | failures seen | silent failures |",
        "|---|---|---:|---|---:|---:|",
    ]
    for d in results:
        for key, mon in d.monitors.items():
            first = _first_alarm(mon)
            q = mon.quality
            lines.append(
                f"| {d.tenant.id} | {key.replace('_', ' ')} | {len(mon.alerts)} | "
                f"{f'`{first[0]}` after {first[1]} tickets' if first else 'none'} | "
                f"{q.seen} of {q.failures} | {q.silent} |"
            )
    lines += [
        "",
        "## Limits",
        "",
        "- The world is a simulation with a deterministic oracle. It is not customer traffic.",
        "- With the stand-in model, the numbers test the platform. They do not measure an agent.",
        "- A real model run replaces these numbers. Refer to `docs/guides/real-model-runs.md`.",
        "",
        "## How to get the same numbers",
        "",
        "```bash",
        "uv run fdeops portfolio --out docs/portfolio/generated",
        "```",
        "",
        "The run IDs change at each run. The numbers do not change, because each run has a seed.",
        "",
    ]
    return "\n".join(lines)


def _lines(path: Path) -> int:
    return sum(1 for _ in path.read_text(encoding="utf-8").splitlines())


def render_case_study(base: DemoResult, new: DemoResult, repo_root: Path) -> str:
    """The deployment case study of a second tenant, with measured onboarding values."""
    t = new.tenant
    root = t.root
    files = sorted(p for p in root.rglob("*") if p.is_file())
    config_files = [p for p in files if p.suffix == ".yaml"]
    kb_files = [p for p in files if p.parent.name == "kb"]
    pack_dir = repo_root / "src" / "fdeops" / "packs" / t.pack.id
    pack_lines = sum(_lines(p) for p in pack_dir.glob("*.py"))
    platform = [p for p in (repo_root / "src" / "fdeops").rglob("*.py") if "packs" not in p.parts]
    platform_lines = sum(_lines(p) for p in platform)
    named = [
        p
        for p in platform
        if "cli" not in p.parts and any(tid in p.read_text() for tid in (t.id, base.tenant.id))
    ]
    incidents = sorted((repo_root / "incidents" / t.id).glob("*.yaml"))
    gates_a = load_gates(base.tenant.root / "gates.yaml")
    gates_b = load_gates(root / "gates.yaml")
    mon_a = load_monitors(base.tenant.root / "monitors.yaml")
    mon_b = load_monitors(root / "monitors.yaml")
    q = t.data_quality

    def gate_row(name: str, a: object, b: object) -> str:
        return f"| {name} | {a} | {b} |"

    lines = [
        *_head([new]),
        f"# Case Study: The {t.config.display_name} Deployment",
        "",
        "*The platform wrote this document from the tenant files and the "
        "records of the flagship demo. The company and its data are fictional.*",
        "",
        "## The customer",
        "",
        f"{t.config.display_name} is the second tenant on the platform. It uses the "
        f"`{t.pack.id}` domain pack. {t.config.notes.strip()}",
        "",
        "## What the deployment needed",
        "",
        "| item | value |",
        "|---|---:|",
        f"| Configuration files (YAML) | {len(config_files)} |",
        f"| Lines in the configuration files | {sum(_lines(p) for p in config_files)} |",
        f"| Knowledge base documents | {len(kb_files)} |",
        f"| Domain pack: lines of Python | {pack_lines} |",
        f"| Platform: lines of Python (not in packs) | {platform_lines} |",
        f"| Platform files that name a tenant | {len(named)} |",
        f"| Scenarios in the pack | {len(t.pack.scenarios())} |",
        f"| Incident files | {len(incidents)} |",
        "",
        "The platform code did not change for this tenant. A new domain needs a pack. A new "
        "tenant in a known domain needs only the configuration files.",
        "",
        "## Differences from the first tenant",
        "",
        f"| setting | {base.tenant.config.display_name} | {t.config.display_name} |",
        "|---|---|---|",
    ]
    if gates_a.task_success and gates_b.task_success:
        lines.append(
            gate_row(
                "minimum lower limit of task success",
                f"{gates_a.task_success.min_lower_limit:.0%}",
                f"{gates_b.task_success.min_lower_limit:.0%}",
            )
        )
    if gates_a.critical_violations and gates_b.critical_violations:
        lines.append(
            gate_row(
                "maximum critical trials",
                gates_a.critical_violations.max_trials,
                gates_b.critical_violations.max_trials,
            )
        )
    if gates_a.latency and gates_b.latency:
        lines.append(
            gate_row(
                "maximum p95 latency (ms)",
                f"{gates_a.latency.max_p95_ms:,.0f}",
                f"{gates_b.latency.max_p95_ms:,.0f}",
            )
        )
    if gates_a.cost and gates_b.cost:
        lines.append(
            gate_row(
                "maximum cost for each resolution",
                f"${gates_a.cost.max_usd_per_resolution:.2f}",
                f"${gates_b.cost.max_usd_per_resolution:.2f}",
            )
        )
    lines += [
        gate_row("monitors", len(mon_a.monitors), len(mon_b.monitors)),
        gate_row("CUSUM alarm level", mon_a.cusum_threshold, mon_b.cusum_threshold),
        gate_row(
            "PII patterns of the tenant",
            len(base.tenant.config.pii.custom),
            len(t.config.pii.custom),
        ),
        gate_row("agent scopes", len(base.tenant.config.agent_scopes), len(t.config.agent_scopes)),
        "",
        "## Data quality at ingest",
        "",
        f"The ingest step loaded {sum(q.loaded.values())} records and isolated "
        f"{sum(q.quarantined.values())}. It found {len(q.issues)} issue(s). Each issue tells "
        "the record, the field and the cause.",
        "",
        "## Result",
        "",
    ]
    lines += [f"- **{s.title}.** {s.text}" for s in new.steps]
    lines += [
        "",
        "## Lessons",
        "",
        "- Tenant settings in files make the differences easy to examine in a review.",
        "- The same incident type (document drift) occurred at the two tenants. The same monitor, "
        "the same diagnosis and the same fix found it.",
        "- A second tenant is the test of a multi-tenant design. Tenant names in platform code "
        "show a design defect. A test finds them.",
        "",
    ]
    return "\n".join(lines)


def write_portfolio(results: Sequence[DemoResult], repo_root: Path, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def put(name: str, text: str) -> None:
        path = out / name
        path.write_text(text, encoding="utf-8")
        written.append(path)

    for d in results:
        inc = d.runs["monitor_test"].incident
        put(f"postmortem-{d.tenant.id}-{inc.id if inc else 'incident'}.md", render_postmortem(d))
        put(
            f"roadmap-{d.tenant.id}.md", "\n".join(_head([d])) + "\n" + d.reports.get("roadmap", "")
        )
    put("benchmark-report.md", render_benchmark(results))
    if len(results) > 1:
        put(
            f"case-study-{results[1].tenant.id}.md",
            render_case_study(results[0], results[1], repo_root),
        )
    return written
