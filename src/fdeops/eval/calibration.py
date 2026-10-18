"""Measure how far an automated judge can be trusted: agreement with human labels on the same
trials, corrected for chance (Cohen's kappa). A judge below the floor may be reported, but must not
gate a release."""

from collections.abc import Mapping

from fdeops.core.model import FrozenModel
from fdeops.eval.stats import cohens_kappa


class CalibrationReport(FrozenModel):
    judge: str
    n: int
    kappa: float
    agreement: float
    confusion: dict[str, dict[str, int]]
    floor: float
    meets_floor: bool


def calibrate(
    judge: str,
    judge_labels: Mapping[str, bool],
    human_labels: Mapping[str, bool],
    floor: float = 0.6,
) -> CalibrationReport:
    keys = sorted(set(judge_labels) & set(human_labels))
    j = [judge_labels[k] for k in keys]
    h = [human_labels[k] for k in keys]
    confusion = {
        "judge_pass": {"human_pass": 0, "human_fail": 0},
        "judge_fail": {"human_pass": 0, "human_fail": 0},
    }
    for jv, hv in zip(j, h, strict=True):
        confusion["judge_pass" if jv else "judge_fail"]["human_pass" if hv else "human_fail"] += 1
    kappa = cohens_kappa(j, h)
    agreement = sum(a == b for a, b in zip(j, h, strict=True)) / len(keys) if keys else 0.0
    return CalibrationReport(
        judge=judge,
        n=len(keys),
        kappa=kappa,
        agreement=agreement,
        confusion=confusion,
        floor=floor,
        meets_floor=bool(keys) and kappa >= floor,
    )
