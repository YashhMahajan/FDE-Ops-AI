"""Monitor a current run against a reference run, and write the report.

A test checks the text.
"""

import json
from pathlib import Path

from fdeops.core.errors import FdeOpsError
from fdeops.core.provenance import Provenance
from fdeops.eval.report import PROVENANCE_NOTE
from fdeops.eval.runner import RunResult
from fdeops.monitor.config import MonitorConfig, load_monitors
from fdeops.monitor.detect import MonitorReport, MonitorResult, detect
from fdeops.monitor.signals import run_signals
from fdeops.tenancy.loader import Tenant


def monitor_runs(
    tenant: Tenant, reference: RunResult, current: RunResult, config: MonitorConfig | None = None
) -> MonitorReport:
    if reference.tenant_id != tenant.id or current.tenant_id != tenant.id:
        raise FdeOpsError("the reference run and the current run must be runs of this tenant")
    config = config or load_monitors(tenant.root / "monitors.yaml")
    cur = run_signals(current)
    results, quality = detect(config, run_signals(reference), cur)
    worst = (
        Provenance.PIPELINE_TEST
        if Provenance.PIPELINE_TEST in (reference.provenance, current.provenance)
        else current.provenance
    )
    return MonitorReport(
        tenant_id=tenant.id,
        reference_run=reference.run_id,
        current_run=current.run_id,
        provenance=worst.value,
        results=tuple(results),
        quality=quality,
        streams={
            s.signal: [t.flags[s.signal] for t in cur]
            for s in config.monitors
            if s.statistic == "rate"
        },
    )


def _fmt(r: MonitorResult, x: float) -> str:
    if r.statistic == "rate":
        return f"{x:.1%}"
    return f"{x:,.0f}"


def _change(r: MonitorResult) -> str:
    unit = "points" if r.statistic == "rate" else "relative"
    scale = 100
    suffix = "" if r.statistic == "rate" else "%"
    return (
        f"{r.change * scale:+.1f}{suffix} ({r.lo * scale:+.1f}{suffix} to "
        f"{r.hi * scale:+.1f}{suffix}, {unit})"
    )


def render_monitor(rep: MonitorReport) -> str:
    prov = Provenance(rep.provenance)
    q = rep.quality
    alerts = rep.alerts
    lines = [
        f"> **Provenance: {prov.value}**. {PROVENANCE_NOTE[prov]}",
        "",
        f"# Production monitor for `{rep.tenant_id}`",
        "",
        f"Reference window: run `{rep.reference_run}`. Current window: run `{rep.current_run}`.",
        "",
        "The monitor uses only signals that a live deployment can see. It does not use the "
        "oracle. An alert occurs only when all of the 95% interval of the change is more than "
        "the tolerance.",
        "",
        "## Alerts",
        "",
    ]
    if alerts:
        for r in alerts:
            delay = (
                f" The sequential detector gave the alarm after {r.detected_after} ticket(s)."
                if r.detected_after
                else ""
            )
            lines.append(
                f"- **{r.severity}** `{r.signal}`: {_fmt(r, r.reference)} to {_fmt(r, r.current)}."
                f"{delay} {r.why}"
            )
    else:
        lines.append("- No alerts. All monitors are in their tolerance or need more samples.")
    lines += [
        "",
        "## All monitors",
        "",
        "| signal | statistic | status | reference | current | change (95% CI) | tolerance |",
        "|---|---|---|---:|---:|---|---:|",
    ]
    for r in rep.results:
        tol = f"{r.tolerance:.0%}"
        lines.append(
            f"| `{r.signal}` | {r.statistic}, {r.direction} | {r.status} | {_fmt(r, r.reference)} "
            f"| {_fmt(r, r.current)} | {_change(r)} | {tol} |"
        )
    lines += [
        "",
        "## Detection quality",
        "",
        "In the simulation, the oracle tells which trials failed. Thus, the platform can measure "
        "how many failures the monitor sees.",
        "",
        f"- Failed trials in the current window: {q.failures} of {q.trials}.",
        f"- Failures with one or more monitored flags: {q.seen}.",
        f"- Silent failures (no flag): {q.silent}. That is {q.silent_rate:.1%} of the traffic, "
        f"and the 95% confidence limit is {q.silent_rate_hi:.1%} at the maximum.",
    ]
    if q.review_sample:
        lines.append(
            f"- Review {q.review_sample} tickets without a flag to see one or more silent "
            "failures with a 95% probability. The monitor cannot find these failures."
        )
    lines += [
        "",
        "| signal | flagged trials | precision | recall |",
        "|---|---:|---:|---:|",
    ]
    for s in q.signals:
        if s.flagged:
            lines.append(f"| `{s.signal}` | {s.flagged} | {s.precision:.0%} | {s.recall:.0%} |")
    lines += [
        "",
        "Precision is the part of the flagged trials that failed. Recall is the part of the "
        "failures that have the flag.",
        "",
        "## Next step",
        "",
        "Run the diagnosis on the dev split of the current window. An alert is a symptom. "
        "It is not a cause."
        if alerts
        else "Continue to monitor. Review a sample of the traffic without a flag.",
        "",
    ]
    return "\n".join(lines)


def save_monitor(rep: MonitorReport, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    (out / "monitor.json").write_text(json.dumps(rep.model_dump(mode="json"), indent=2))
    (out / "monitor.md").write_text(render_monitor(rep), encoding="utf-8")
    return out
