"""Gate evaluation. Each gate uses a confidence limit, and each result keeps its evidence.

A gate that the platform cannot measure fails, unless the tenant configuration accepts it and
explains why. Thus, a missing measurement can never look like a pass.
"""

import math

from fdeops.core.errors import ConfigError
from fdeops.eval.compare import compare_runs
from fdeops.eval.report import summarize
from fdeops.eval.runner import RunResult
from fdeops.release.models import GateConfig, GateResult, GateStatus
from fdeops.tenancy.loader import Tenant


def _result(gate: str, status: GateStatus, observed: str, threshold: str, why: str) -> GateResult:
    return GateResult(
        gate=gate,
        status=status,
        passed=status in ("pass", "not_applicable"),
        observed=observed,
        threshold=threshold,
        why=why,
    )


def run_cost_usd(run: RunResult, cfg: GateConfig) -> float | None:
    if cfg.pricing is None:
        return None
    p = cfg.pricing
    return sum(
        r.episode.usage.input_tokens / 1e6 * p.usd_per_mtok_input
        + r.episode.usage.output_tokens / 1e6 * p.usd_per_mtok_output
        for r in run.results
    )


def evaluate_gates(
    tenant: Tenant,
    cfg: GateConfig,
    candidate: RunResult,
    baseline: RunResult | None,
    *,
    integration_passed: bool | None = None,
    regression_passed: bool | None = None,
    judge_kappa: float | None = None,
) -> list[GateResult]:
    if candidate.dataset_split != "test":
        raise ConfigError(
            "gates use the test split only. The candidate run uses the "
            f"{candidate.dataset_split} split."
        )
    if candidate.tenant_id != tenant.id:
        raise ConfigError(f"the candidate run belongs to tenant {candidate.tenant_id!r}")
    if baseline is not None and baseline.dataset_hash != candidate.dataset_hash:
        raise ConfigError("the baseline run must use the same dataset as the candidate run")
    s = summarize(candidate)
    out: list[GateResult] = []
    if (g := cfg.task_success) is not None:
        ok = s.overall.ci_lo >= g.min_lower_limit
        out.append(
            _result(
                "task_success",
                "pass" if ok else "fail",
                f"lower limit {s.overall.ci_lo:.1%} (rate {s.overall.rate:.1%})",
                f"lower limit {g.min_lower_limit:.0%} or more",
                g.why,
            )
        )
    if (c := cfg.critical_violations) is not None:
        ok = s.critical_trials <= c.max_trials and s.critical_rate_upper <= c.max_upper_limit
        out.append(
            _result(
                "critical_violations",
                "pass" if ok else "fail",
                f"{s.critical_trials} trial(s), maximum limit {s.critical_rate_upper:.1%}",
                f"at most {c.max_trials} trial(s) and {c.max_upper_limit:.0%}",
                c.why,
            )
        )
    if (n := cfg.non_inferiority) is not None:
        if baseline is None:
            out.append(
                _result(
                    "non_inferiority",
                    "not_applicable",
                    "no production baseline",
                    f"margin {n.margin:.0%}",
                    n.why,
                )
            )
        else:
            cmp = compare_runs(baseline, candidate)
            worse = {
                t: d for t in n.slices if (d := cmp.by_tag.get(t)) is not None and d.lo < -n.margin
            }
            observed = (
                ", ".join(
                    f"{t}: {cmp.by_tag[t].mean:+.3f} (lower {cmp.by_tag[t].lo:+.3f})"
                    for t in n.slices
                    if t in cmp.by_tag
                )
                or "no protected slices"
            )
            out.append(
                _result(
                    "non_inferiority",
                    "fail" if worse else "pass",
                    observed,
                    f"lower limit -{n.margin:.2f} or more on {list(n.slices)}",
                    n.why,
                )
            )
    if (lt := cfg.latency) is not None:
        p95 = s.metrics.get("latency_p95_ms", math.nan)
        status: GateStatus = (
            "not_measured" if math.isnan(p95) else ("pass" if p95 <= lt.max_p95_ms else "fail")
        )
        out.append(
            _result(
                "latency", status, f"p95 {p95:,.0f} ms", f"at most {lt.max_p95_ms:,.0f} ms", lt.why
            )
        )
    if (co := cfg.cost) is not None:
        total = run_cost_usd(candidate, cfg)
        resolved = s.overall.successes
        if total is None or resolved == 0:
            status = "pass" if co.allow_unmeasured else "not_measured"
            out.append(
                _result(
                    "cost",
                    status,
                    "no price for the model",
                    f"at most ${co.max_usd_per_resolution:.3f}",
                    co.why,
                )
            )
        else:
            per = total / resolved
            out.append(
                _result(
                    "cost",
                    "pass" if per <= co.max_usd_per_resolution else "fail",
                    f"${per:.4f} for each resolution ({cfg.pricing.basis if cfg.pricing else ''})",
                    f"at most ${co.max_usd_per_resolution:.3f}",
                    co.why,
                )
            )
    for name, value in (
        ("integration_suite", integration_passed),
        ("regression_suite", regression_passed),
    ):
        req = getattr(cfg, name)
        if req is None or not req.required:
            continue
        status = "fail" if value is None else ("pass" if value else "fail")
        observed = "not run" if value is None else ("passed" if value else "failed")
        out.append(_result(name, status, observed, "must pass", req.why))
    if (k := cfg.judge_calibration) is not None:
        uses_judge = any(sc.name.startswith("judge.") for r in candidate.results for sc in r.scores)
        if not uses_judge:
            out.append(
                _result(
                    "judge_calibration",
                    "not_applicable",
                    "no judge in the run",
                    f"kappa {k.min_kappa} or more",
                    k.why,
                )
            )
        else:
            status = (
                "fail"
                if judge_kappa is None
                else ("pass" if judge_kappa >= k.min_kappa else "fail")
            )
            out.append(
                _result(
                    "judge_calibration",
                    status,
                    f"kappa {judge_kappa}",
                    f"kappa {k.min_kappa} or more",
                    k.why,
                )
            )
    if (pr := cfg.pii_redaction) is not None and pr.required:
        ok = tenant.config.pii.redact
        out.append(
            _result(
                "pii_redaction",
                "pass" if ok else "fail",
                "on" if ok else "off",
                "must be on",
                pr.why,
            )
        )
    return out
