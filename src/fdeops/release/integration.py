"""The integration suite: the agent must survive faults without a crash or a duplicated action.

The suite runs a sample of cases under several fault profiles. It does not measure quality. It
measures robustness: the episode ends, the audit chain is correct, and an operation that changes
data never occurs two times for one request.
"""

from collections import Counter

from fdeops.agent.config import AgentConfig
from fdeops.connectors.faults import FaultRule
from fdeops.core.model import FrozenModel
from fdeops.eval.runner import run_eval
from fdeops.llm.types import LLMClient
from fdeops.tenancy.loader import Tenant
from fdeops.world.cases import Case
from fdeops.world.dataset import Dataset

PROFILES: dict[str, tuple[FaultRule, ...]] = {
    "timeout_after_success": (
        FaultRule(
            op="*", kind="timeout_after_success", probability=0.7, times=2, only_mutating=True
        ),
    ),
    "upstream_errors": (
        FaultRule(op="*", kind="error_5xx", probability=0.3),
        FaultRule(op="*", kind="rate_limit", probability=0.1),
    ),
    "bad_responses": (
        FaultRule(op="*", kind="malformed", probability=0.2),
        FaultRule(op="*", kind="timeout", probability=0.1),
    ),
}


class IntegrationCheck(FrozenModel):
    name: str
    passed: bool
    detail: str
    failures: tuple[str, ...] = ()


class IntegrationReport(FrozenModel):
    tenant_id: str
    agent_config_hash: str
    n_episodes: int
    checks: tuple[IntegrationCheck, ...]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)


def _sample(ds: Dataset, n: int) -> Dataset:
    """Prefer cases that change data, one scenario after the other.

    Retries can cause harm only where data changes. Some APIs have an invariant that blocks a
    second identical change (a full refund), and others do not (a data export). A rotation across
    scenarios makes sure that the sample has both types.
    """
    by_scenario: dict[str, list[Case]] = {}
    for c in sorted(ds.cases, key=lambda c: (not c.expected.changes, c.scenario, c.id)):
        by_scenario.setdefault(c.scenario, []).append(c)
    queues = list(by_scenario.values())
    picked: list[Case] = []
    while len(picked) < n and any(queues):
        for q in queues:
            if q and len(picked) < n:
                picked.append(q.pop(0))
    return ds.model_copy(update={"cases": tuple(picked)})


def run_integration_suite(
    tenant: Tenant, config: AgentConfig, dataset: Dataset, llm: LLMClient, sample: int = 20
) -> IntegrationReport:
    ds = _sample(dataset, sample)
    crashes: list[str] = []
    duplicates: list[str] = []
    audit: list[str] = []
    injected = 0
    episodes = 0
    for name, rules in PROFILES.items():
        run = run_eval(tenant, config, ds, llm, faults=rules)
        for r in run.results:
            episodes += 1
            ep = r.episode
            injected += len(ep.faults_injected)
            if ep.error is not None and ep.outcome == "model_error":
                crashes.append(f"{name}:{r.case_id}: {ep.error}")
            if not ep.audit_ok:
                audit.append(f"{name}:{r.case_id}")
            created = Counter(
                c.collection
                for c in ep.changes
                if c.kind == "created" and tenant.pack.is_outcome_change(c)
            )
            case = next(c for c in ds.cases if c.id == r.case_id)
            allowed = Counter(e.collection for e in case.expected.changes if e.kind == "created")
            over = [k for k, v in created.items() if v > max(1, allowed.get(k, 0))]
            if over:
                duplicates.append(f"{name}:{r.case_id}: {over}")
    checks = (
        IntegrationCheck(
            name="faults_injected",
            passed=injected > 0,
            detail=f"{injected} faults in {episodes} episodes",
        ),
        IntegrationCheck(
            name="no_crash",
            passed=not crashes,
            detail=f"{len(crashes)} episode(s) ended with an error",
            failures=tuple(crashes[:20]),
        ),
        IntegrationCheck(
            name="no_duplicate_action",
            passed=not duplicates,
            detail=f"{len(duplicates)} episode(s) did one task more than one time",
            failures=tuple(duplicates[:20]),
        ),
        IntegrationCheck(
            name="audit_chain",
            passed=not audit,
            detail=f"{len(audit)} episode(s) with a broken audit chain",
            failures=tuple(audit[:20]),
        ),
    )
    return IntegrationReport(
        tenant_id=tenant.id,
        agent_config_hash=config.content_hash,
        n_episodes=episodes,
        checks=checks,
    )
