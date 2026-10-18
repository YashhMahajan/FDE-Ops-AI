from collections import Counter, defaultdict

from fdeops.core.model import FrozenModel
from fdeops.diagnose.taxonomy import Evidence, FailureClass, FailureLabel
from fdeops.eval.runner import RunResult


class FailureCluster(FrozenModel):
    id: str
    failure_class: FailureClass
    scenario: str
    n_trials: int
    n_cases: int
    case_ids: tuple[str, ...]
    share_of_failures: float
    share_of_scenario_trials: float
    tags: dict[str, int]
    secondary: dict[str, int]
    examples: tuple[Evidence, ...]


def cluster_failures(labels: list[FailureLabel], run: RunResult) -> list[FailureCluster]:
    """Group failures by primary class and scenario. The largest clusters come first."""
    groups: dict[tuple[FailureClass, str], list[FailureLabel]] = defaultdict(list)
    for lbl in labels:
        groups[(lbl.primary, lbl.scenario)].append(lbl)
    per_scenario = Counter(r.scenario for r in run.results)
    total = len(labels) or 1
    out = []
    for (cls, scenario), items in groups.items():
        cases = tuple(sorted({i.case_id for i in items}))
        out.append(
            FailureCluster(
                id=f"{cls.value}:{scenario}",
                failure_class=cls,
                scenario=scenario,
                n_trials=len(items),
                n_cases=len(cases),
                case_ids=cases,
                share_of_failures=len(items) / total,
                share_of_scenario_trials=len(items) / per_scenario[scenario],
                tags=dict(Counter(t for i in items for t in i.tags)),
                secondary=dict(Counter(s.value for i in items for s in i.secondary)),
                examples=tuple(e for i in items[:2] for e in i.evidence[:2]),
            )
        )
    out.sort(key=lambda c: (-c.n_trials, c.id))
    return out
