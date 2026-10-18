"""Paired comparison of two runs on the same dataset: is B better or worse than A, where, and how
sure are we?"""

from collections import defaultdict

from fdeops.core.errors import ConfigError
from fdeops.core.model import FrozenModel
from fdeops.eval.runner import RunResult
from fdeops.eval.stats import DiffEstimate, holm, mcnemar_exact, paired_bootstrap_diff


class Comparison(FrozenModel):
    a_run_id: str
    b_run_id: str
    a_config: str
    b_config: str
    n_pairs: int
    """Number of paired *cases*. Trials of one case are averaged first: they are correlated, so
    they must not count as independent evidence."""
    trials: int
    a_rate: float
    b_rate: float
    diff: DiffEstimate
    a_only: int
    """Cases where A's mean success is higher."""
    b_only: int
    mcnemar_p: float
    """Exact sign test on discordant cases (equals McNemar's test when trials == 1)."""
    by_scenario: dict[str, DiffEstimate]
    scenario_p: dict[str, float]
    holm_p: dict[str, float]


def _per_case(run: RunResult) -> dict[str, tuple[str, float]]:
    acc: dict[str, list[bool]] = defaultdict(list)
    scenario: dict[str, str] = {}
    for r in run.results:
        acc[r.case_id].append(r.success)
        scenario[r.case_id] = r.scenario
    return {c: (scenario[c], sum(v) / len(v)) for c, v in acc.items()}


def compare_runs(a: RunResult, b: RunResult, seed: int = 0) -> Comparison:
    if a.dataset_hash != b.dataset_hash:
        raise ConfigError(
            "runs used different datasets; a paired comparison is not valid "
            f"({a.dataset_ref} vs {b.dataset_ref})"
        )
    pa, pb = _per_case(a), _per_case(b)
    keys = sorted(set(pa) & set(pb))
    xa = [pa[k][1] for k in keys]
    xb = [pb[k][1] for k in keys]
    a_only = sum(1 for x, y in zip(xa, xb, strict=True) if x > y)
    b_only = sum(1 for x, y in zip(xa, xb, strict=True) if y > x)
    groups: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for k, x, y in zip(keys, xa, xb, strict=True):
        groups[pa[k][0]].append((x, y))
    by_scenario, scenario_p = {}, {}
    for name, pairs in sorted(groups.items()):
        ga, gb = [p[0] for p in pairs], [p[1] for p in pairs]
        by_scenario[name] = paired_bootstrap_diff(ga, gb, n_resamples=2000, seed=seed)
        scenario_p[name] = mcnemar_exact(sum(x > y for x, y in pairs), sum(y > x for x, y in pairs))
    adjusted = holm(list(scenario_p.values()))
    n = len(keys)
    return Comparison(
        a_run_id=a.run_id,
        b_run_id=b.run_id,
        a_config=a.agent_config.id,
        b_config=b.agent_config.id,
        n_pairs=n,
        trials=min(a.trials, b.trials),
        a_rate=sum(xa) / n if n else 0.0,
        b_rate=sum(xb) / n if n else 0.0,
        diff=paired_bootstrap_diff(xa, xb, seed=seed),
        a_only=a_only,
        b_only=b_only,
        mcnemar_p=mcnemar_exact(a_only, b_only),
        by_scenario=by_scenario,
        scenario_p=scenario_p,
        holm_p=dict(zip(scenario_p, adjusted, strict=True)),
    )


def verdict(c: Comparison, alpha: float = 0.05) -> str:
    if c.diff.hi < 0 and c.mcnemar_p < alpha:
        return "Regression: B is worse than A"
    if c.diff.lo > 0 and c.mcnemar_p < alpha:
        return "Improvement: B is better than A"
    return "No credible difference at this sample size"


def render_comparison(c: Comparison) -> str:
    lines = [
        f"# {c.b_config} (B) vs {c.a_config} (A)",
        "",
        f"**{verdict(c)}.** Success {c.a_rate:.1%} → {c.b_rate:.1%} over {c.n_pairs} paired "
        f"cases ({c.trials} trial(s) each, averaged per case); difference {c.diff.mean:+.3f} "
        f"(95% CI {c.diff.lo:+.3f} to {c.diff.hi:+.3f}); "
        f"discordant cases A-better={c.a_only}, B-better={c.b_only}; exact sign test "
        f"p={c.mcnemar_p:.4f}.",
        "",
        "| scenario | diff | 95% CI | p | Holm p |",
        "|---|---:|---|---:|---:|",
    ]
    for name, d in c.by_scenario.items():
        lines.append(
            f"| {name} | {d.mean:+.3f} | {d.lo:+.3f} to {d.hi:+.3f} | "
            f"{c.scenario_p[name]:.4f} | {c.holm_p[name]:.4f} |"
        )
    return "\n".join(lines) + "\n"
