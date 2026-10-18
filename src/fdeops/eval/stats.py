"""Statistics for honest comparisons.

Small, explicit implementations of the methods the gates and reports rely on. Each docstring
says when the method applies, because the point is to be able to defend a number.
"""

import math
from collections.abc import Sequence

import numpy as np
from scipy import stats as sps

from fdeops.core.model import FrozenModel


def _z(confidence: float) -> float:
    return float(sps.norm.ppf(1 - (1 - confidence) / 2))


def wilson_interval(successes: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a binomial rate. Unlike the normal approximation it behaves at
    0%/100% and small n, which is exactly where release gates live."""
    if n == 0:
        return (0.0, 1.0)
    z = _z(confidence)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


class DiffEstimate(FrozenModel):
    mean: float
    lo: float
    hi: float
    n: int


def paired_bootstrap_diff(
    a: Sequence[float],
    b: Sequence[float],
    n_resamples: int = 10_000,
    confidence: float = 0.95,
    seed: int = 0,
) -> DiffEstimate:
    """Percentile bootstrap CI for mean(b - a) over paired observations (same cases under two
    configurations). Pairing removes case-difficulty variance, so it needs far fewer cases than
    comparing two independent rates."""
    if len(a) != len(b):
        raise ValueError("paired samples must have equal length")
    n = len(a)
    if n == 0:
        return DiffEstimate(mean=0.0, lo=0.0, hi=0.0, n=0)
    diffs = np.asarray(b, dtype=float) - np.asarray(a, dtype=float)
    rng = np.random.default_rng(seed)
    means = np.empty(n_resamples)
    chunk = max(1, 2_000_000 // n)
    for start in range(0, n_resamples, chunk):
        stop = min(n_resamples, start + chunk)
        means[start:stop] = diffs[rng.integers(0, n, size=(stop - start, n))].mean(axis=1)
    alpha = (1 - confidence) / 2
    lo, hi = np.quantile(means, [alpha, 1 - alpha])
    return DiffEstimate(mean=float(diffs.mean()), lo=float(lo), hi=float(hi), n=n)


def mcnemar_exact(b: int, c: int) -> float:
    """Exact two-sided McNemar test on discordant pairs: b = A passed & B failed, c = the reverse.
    Concordant pairs carry no information about which configuration is better."""
    n = b + c
    if n == 0:
        return 1.0
    return float(min(1.0, 2 * sps.binom.cdf(min(b, c), n, 0.5)))


def pass_hat_k(successes_per_case: Sequence[int], n_trials: int, k: int) -> float:
    """Probability that k independent trials of a case *all* succeed, averaged over cases, using the
    unbiased estimator C(c, k) / C(n, k). It measures reliability, which pass@1 hides."""
    if k > n_trials:
        raise ValueError("k cannot exceed the number of trials")
    if not successes_per_case:
        return 0.0
    total = math.comb(n_trials, k)
    return sum(math.comb(c, k) / total for c in successes_per_case) / len(successes_per_case)


def holm(pvalues: Sequence[float]) -> list[float]:
    """Holm step-down adjustment: controls family-wise error across many slices without
    Bonferroni's full conservatism."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def rule_of_three_upper(n: int) -> float:
    """~95% upper bound on an event rate when zero events were seen in n trials. 'No critical
    violations in 50 cases' still allows a true rate of up to 6%, and gates must say so."""
    return 1.0 if n <= 3 else 3.0 / n


def cohens_kappa(a: Sequence[bool], b: Sequence[bool]) -> float:
    """Chance-corrected agreement between two raters (e.g. an LLM judge and a human)."""
    if len(a) != len(b):
        raise ValueError("label sequences must have equal length")
    n = len(a)
    if n == 0:
        return 0.0
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)


def n_for_ci_half_width(half_width: float, p: float = 0.5, confidence: float = 0.95) -> int:
    """Cases needed so a rate's 95% CI is at most +/- half_width (normal approximation)."""
    z = _z(confidence)
    return math.ceil(z * z * p * (1 - p) / (half_width * half_width))


def mde_two_proportions(n: int, p_base: float, alpha: float = 0.05, power: float = 0.8) -> float:
    """Smallest drop from p_base detectable with n cases per arm (two-sided, unpaired; a paired
    design does at least this well). Answers 'is our test set big enough to catch a regression?'"""
    za, zb = _z(1 - alpha), float(sps.norm.ppf(power))

    def needed(delta: float) -> float:
        p2 = p_base - delta
        pbar = (p_base + p2) / 2
        top = za * math.sqrt(2 * pbar * (1 - pbar)) + zb * math.sqrt(
            p_base * (1 - p_base) + p2 * (1 - p2)
        )
        return (top / delta) ** 2

    lo, hi = 1e-6, p_base
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if needed(mid) > n else (lo, mid)
    return hi
