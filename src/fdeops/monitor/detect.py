"""Detection: compare a current traffic window with a reference window.

Two methods operate together:

- An interval test for each monitor. A rate monitor uses the Newcombe interval of the change. A
  value monitor uses a bootstrap interval of the ratio. An alert needs the full interval to be
  outside the tolerance, not only the point estimate.
- A Bernoulli CUSUM for each rate monitor, in ticket order. It tells how many tickets of the
  current window go by before the alarm. This is the detection delay.
"""

import math
from collections.abc import Sequence
from typing import Literal

import numpy as np

from fdeops.core.model import FrozenModel
from fdeops.eval.stats import newcombe_diff, wilson_interval
from fdeops.monitor.config import MonitorConfig, MonitorSpec
from fdeops.monitor.signals import RATE_SIGNALS, VALUE_SIGNALS, TrialSignals

Status = Literal["alert", "ok", "too few samples", "not measured"]
BOOTSTRAP_DRAWS = 2000


class MonitorResult(FrozenModel):
    signal: str
    description: str
    statistic: str
    direction: str
    severity: str
    why: str
    status: Status
    reference: float
    current: float
    change: float
    lo: float
    hi: float
    tolerance: float
    n_reference: int
    n_current: int
    detected_after: int | None = None
    """For a rate monitor: the number of current tickets before the CUSUM alarm."""


def cusum_alarm(
    flags: Sequence[bool], p0: float, shift: float, direction: str, threshold: float
) -> int | None:
    """Bernoulli CUSUM. It returns the 1-based ticket number of the alarm, or None.

    Each ticket adds its log-likelihood ratio of the changed rate p1 against the reference rate p0.
    The sum does not go below zero. The alarm occurs when the sum is more than the threshold.
    """
    p0 = min(max(p0, 0.005), 0.995)
    p1 = p0 + shift if direction == "up" else p0 - shift
    p1 = min(max(p1, 0.001), 0.999)
    w1 = math.log(p1 / p0)
    w0 = math.log((1 - p1) / (1 - p0))
    s = 0.0
    for i, x in enumerate(flags, start=1):
        s = max(0.0, s + (w1 if x else w0))
        if s > threshold:
            return i
    return None


def _rate(
    spec: MonitorSpec, ref: list[TrialSignals], cur: list[TrialSignals], threshold: float
) -> MonitorResult:
    rf = [t.flags[spec.signal] for t in ref]
    cf = [t.flags[spec.signal] for t in cur]
    x1, n1, x2, n2 = sum(cf), len(cf), sum(rf), len(rf)
    d, lo, hi = newcombe_diff(x1, n1, x2, n2)
    p_ref = x2 / n2 if n2 else 0.0
    if spec.direction == "down":
        d, lo, hi = -d, -hi, -lo
    status: Status
    if min(n1, n2) < spec.min_samples:
        status = "too few samples"
    else:
        status = "alert" if lo > spec.tolerance else "ok"
    detected = cusum_alarm(cf, p_ref, spec.shift, spec.direction, threshold)
    return MonitorResult(
        signal=spec.signal,
        description=RATE_SIGNALS[spec.signal],
        statistic="rate",
        direction=spec.direction,
        severity=spec.severity,
        why=spec.why,
        status=status,
        reference=p_ref,
        current=x1 / n1 if n1 else 0.0,
        change=d,
        lo=lo,
        hi=hi,
        tolerance=spec.tolerance,
        n_reference=n2,
        n_current=n1,
        detected_after=detected if status == "alert" else None,
    )


def _stat(values: np.ndarray, statistic: str) -> np.ndarray:
    if statistic == "p95":
        return np.asarray(np.percentile(values, 95, axis=-1), dtype=float)
    return np.asarray(values.mean(axis=-1), dtype=float)


def _value(spec: MonitorSpec, ref: list[TrialSignals], cur: list[TrialSignals]) -> MonitorResult:
    rv = np.array([t.values[spec.signal] for t in ref], dtype=float)
    cv = np.array([t.values[spec.signal] for t in cur], dtype=float)
    base = dict(
        signal=spec.signal,
        description=VALUE_SIGNALS[spec.signal],
        statistic=spec.statistic,
        direction=spec.direction,
        severity=spec.severity,
        why=spec.why,
        tolerance=spec.tolerance,
        n_reference=len(rv),
        n_current=len(cv),
    )
    if min(len(rv), len(cv)) < spec.min_samples:
        return MonitorResult(
            status="too few samples", reference=0, current=0, change=0, lo=0, hi=0, **base
        )
    r0, c0 = float(_stat(rv, spec.statistic)), float(_stat(cv, spec.statistic))
    if r0 <= 0:
        return MonitorResult(
            status="not measured", reference=r0, current=c0, change=0, lo=0, hi=0, **base
        )
    rng = np.random.default_rng(0)
    rs = _stat(rv[rng.integers(0, len(rv), (BOOTSTRAP_DRAWS, len(rv)))], spec.statistic)
    cs = _stat(cv[rng.integers(0, len(cv), (BOOTSTRAP_DRAWS, len(cv)))], spec.statistic)
    ratio = cs / np.maximum(rs, 1e-12) - 1
    if spec.direction == "down":
        ratio = -ratio
    lo, hi = (float(x) for x in np.percentile(ratio, [2.5, 97.5]))
    change = (c0 / r0 - 1) * (1 if spec.direction == "up" else -1)
    return MonitorResult(
        status="alert" if lo > spec.tolerance else "ok",
        reference=r0,
        current=c0,
        change=change,
        lo=lo,
        hi=hi,
        **base,
    )


class SignalQuality(FrozenModel):
    """How well one signal predicts a real failure. The oracle is known only in the simulation."""

    signal: str
    flagged: int
    true_positive: int
    precision: float
    recall: float


class DetectionQuality(FrozenModel):
    failures: int
    trials: int
    seen: int
    """Failures with one or more monitored flags."""
    silent: int
    silent_rate: float
    silent_rate_hi: float
    review_sample: int | None
    """Tickets to review for a 95% probability to see one silent failure. None: no failures."""
    signals: tuple[SignalQuality, ...]


def detection_quality(cur: list[TrialSignals], monitored: Sequence[str]) -> DetectionQuality:
    failures = [t for t in cur if t.failed]
    per = []
    for name in RATE_SIGNALS:
        flagged = [t for t in cur if t.flags[name]]
        tp = sum(t.failed for t in flagged)
        per.append(
            SignalQuality(
                signal=name,
                flagged=len(flagged),
                true_positive=tp,
                precision=tp / len(flagged) if flagged else 0.0,
                recall=tp / len(failures) if failures else 0.0,
            )
        )
    seen = sum(any(t.flags[m] for m in monitored) for t in failures)
    silent = len(failures) - seen
    rate = silent / len(cur) if cur else 0.0
    review = math.ceil(math.log(0.05) / math.log(1 - rate)) if 0 < rate < 1 else None
    return DetectionQuality(
        failures=len(failures),
        trials=len(cur),
        seen=seen,
        silent=silent,
        silent_rate=rate,
        silent_rate_hi=wilson_interval(silent, len(cur))[1],
        review_sample=review,
        signals=tuple(per),
    )


class MonitorReport(FrozenModel):
    tenant_id: str
    reference_run: str
    current_run: str
    provenance: str
    results: tuple[MonitorResult, ...]
    quality: DetectionQuality
    streams: dict[str, list[bool]] = {}
    """The flag of each rate signal for each ticket of the current window, in ticket order."""

    @property
    def alerts(self) -> list[MonitorResult]:
        return [r for r in self.results if r.status == "alert"]


def detect(
    config: MonitorConfig,
    ref: list[TrialSignals],
    cur: list[TrialSignals],
) -> tuple[list[MonitorResult], DetectionQuality]:
    results = [
        _rate(s, ref, cur, config.cusum_threshold) if s.statistic == "rate" else _value(s, ref, cur)
        for s in config.monitors
    ]
    monitored = [s.signal for s in config.monitors if s.statistic == "rate"]
    return results, detection_quality(cur, monitored)
