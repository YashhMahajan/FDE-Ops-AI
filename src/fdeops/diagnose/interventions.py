"""Counterfactual interventions: replay the cases of a cluster with one change.

An intervention changes one part of the agent configuration. If the change fixes the cluster and
does not break the control cases, the evidence confirms the hypothesis. A fix that only exists in a
diagnostic setting (for example, oracle retrieval) can confirm a cause, but it is not a deployable
fix.
"""

import hashlib
from collections import defaultdict
from enum import StrEnum
from typing import Any

from fdeops.agent.config import apply_patch
from fdeops.core.errors import ConfigError
from fdeops.core.model import FrozenModel
from fdeops.core.provenance import Provenance
from fdeops.diagnose.classify import classify_run
from fdeops.diagnose.clusters import FailureCluster, cluster_failures
from fdeops.diagnose.taxonomy import FailureClass, FailureLabel
from fdeops.eval.runner import RunResult, run_eval
from fdeops.eval.stats import wilson_interval
from fdeops.llm.types import LLMClient
from fdeops.tenancy.loader import Tenant
from fdeops.world.dataset import Dataset

MIN_CASES = 3
MIN_FIX_LO = 0.5
MAX_REGRESSION_HI = 0.2


class Verdict(StrEnum):
    CONFIRMED = "confirmed by intervention"
    SUPPORTED = "supported by evidence"
    INCONCLUSIVE = "inconclusive"


class Intervention(FrozenModel):
    id: str
    description: str
    patch: dict[str, Any]
    applies_to: tuple[FailureClass, ...]
    deployable: bool = True


PLAYBOOK: tuple[Intervention, ...] = (
    Intervention(
        id="freshness_filter",
        description="Remove superseded sections at query time.",
        patch={"retrieval": {"freshness_filter": True}},
        applies_to=(FailureClass.STALE_KNOWLEDGE,),
    ),
    Intervention(
        id="current_index_only",
        description="Index only the current version of each section.",
        patch={"retrieval": {"include_superseded": False}},
        applies_to=(FailureClass.STALE_KNOWLEDGE,),
    ),
    Intervention(
        id="oracle_retrieval",
        description="Give the gold sections as the only context (diagnostic ceiling).",
        patch={"oracle_context": True},
        applies_to=(
            FailureClass.STALE_KNOWLEDGE,
            FailureClass.RETRIEVAL_MISS,
            FailureClass.GROUNDING_FAILURE,
        ),
        deployable=False,
    ),
    Intervention(
        id="bm25_retrieval",
        description="Use lexical retrieval only.",
        patch={"retrieval": {"mode": "bm25"}},
        applies_to=(FailureClass.RETRIEVAL_MISS, FailureClass.GROUNDING_FAILURE),
    ),
    Intervention(
        id="larger_top_k",
        description="Give 8 sections to the agent, not 4.",
        patch={"retrieval": {"top_k": 8}},
        applies_to=(FailureClass.RETRIEVAL_MISS, FailureClass.GROUNDING_FAILURE),
    ),
    Intervention(
        id="enforce_guardrail",
        description="Let the policy monitor stop critical violations.",
        patch={"policy_guardrail": "enforce"},
        applies_to=(
            FailureClass.POLICY_VIOLATION,
            FailureClass.PERMISSION_VIOLATION,
            FailureClass.INJECTION_FOLLOWED,
            FailureClass.MISSED_ESCALATION,
        ),
    ),
    Intervention(
        id="more_retries",
        description="Let connectors try 5 times, not 3.",
        patch={"retry": {"max_attempts": 5}},
        applies_to=(FailureClass.UNHANDLED_TOOL_ERROR,),
    ),
    Intervention(
        id="larger_step_budget",
        description="Let the agent use 14 steps, not 8.",
        patch={"max_steps": 14},
        applies_to=(FailureClass.TIMEOUT_OR_BUDGET,),
    ),
)


def candidates(cluster: FailureCluster) -> list[Intervention]:
    return [i for i in PLAYBOOK if cluster.failure_class in i.applies_to]


class InterventionResult(FrozenModel):
    cluster_id: str
    intervention_id: str
    description: str
    deployable: bool
    config_hash: str
    n_cases: int
    fixed: int
    fix_rate: float
    fix_ci: tuple[float, float]
    n_control: int
    regressions: int
    regression_rate: float
    regression_ci: tuple[float, float]


class ClusterDiagnosis(FrozenModel):
    cluster: FailureCluster
    hypotheses: tuple[str, ...]
    results: tuple[InterventionResult, ...]
    verdict: Verdict
    confirmed_by: str | None
    recommended_fix: str | None
    rationale: str


class Diagnosis(FrozenModel):
    run_id: str
    tenant_id: str
    agent_config_id: str
    dataset_ref: str
    split: str
    provenance: Provenance
    n_trials: int
    n_failures: int
    labels: tuple[FailureLabel, ...]
    clusters: tuple[ClusterDiagnosis, ...]
    warnings: tuple[str, ...]


def verdict_for(
    n_cases: int, fix_ci: tuple[float, float], regression_ci: tuple[float, float]
) -> Verdict:
    if n_cases < MIN_CASES:
        return Verdict.INCONCLUSIVE
    if fix_ci[0] >= MIN_FIX_LO and regression_ci[1] <= MAX_REGRESSION_HI:
        return Verdict.CONFIRMED
    return Verdict.SUPPORTED


def _all_trials_pass(run: RunResult) -> dict[str, bool]:
    per: dict[str, list[bool]] = defaultdict(list)
    for r in run.results:
        per[r.case_id].append(r.success)
    return {c: all(v) for c, v in per.items()}


def _subset(ds: Dataset, ids: set[str]) -> Dataset:
    return ds.model_copy(update={"cases": tuple(c for c in ds.cases if c.id in ids)})


def _control_ids(run: RunResult, max_control: int) -> set[str]:
    passing = sorted(
        (c for c, ok in _all_trials_pass(run).items() if ok),
        key=lambda c: hashlib.sha256(c.encode()).hexdigest(),
    )
    return set(passing[:max_control])


def run_intervention(
    tenant: Tenant,
    run: RunResult,
    dataset: Dataset,
    cluster: FailureCluster,
    intervention: Intervention,
    llm: LLMClient,
    control: set[str],
) -> InterventionResult:
    config = apply_patch(run.agent_config, intervention.patch)
    target = set(cluster.case_ids)
    rerun = run_eval(
        tenant,
        config,
        _subset(dataset, target | control),
        llm,
        trials=run.trials,
        faults=run.faults,
        llm_mode=run.llm_mode,
        llm_settings=run.llm_settings,
    )
    passed = _all_trials_pass(rerun)
    fixed = sum(passed.get(c, False) for c in target)
    regressions = sum(not passed.get(c, False) for c in control)
    fix_ci = wilson_interval(fixed, len(target))
    reg_ci = wilson_interval(regressions, len(control)) if control else (0.0, 1.0)
    return InterventionResult(
        cluster_id=cluster.id,
        intervention_id=intervention.id,
        description=intervention.description,
        deployable=intervention.deployable,
        config_hash=config.content_hash,
        n_cases=len(target),
        fixed=fixed,
        fix_rate=fixed / len(target),
        fix_ci=fix_ci,
        n_control=len(control),
        regressions=regressions,
        regression_rate=regressions / len(control) if control else 0.0,
        regression_ci=reg_ci,
    )


def _diagnose_cluster(
    tenant: Tenant,
    run: RunResult,
    dataset: Dataset,
    cluster: FailureCluster,
    llm: LLMClient,
    control: set[str],
) -> ClusterDiagnosis:
    options = candidates(cluster)
    results = tuple(
        run_intervention(tenant, run, dataset, cluster, i, llm, control) for i in options
    )
    graded = [(r, verdict_for(cluster.n_cases, r.fix_ci, r.regression_ci)) for r in results]
    confirming = [r for r, v in graded if v == Verdict.CONFIRMED]
    if cluster.n_cases < MIN_CASES:
        verdict = Verdict.INCONCLUSIVE
        rationale = (
            f"The cluster has {cluster.n_cases} case(s). A verdict needs {MIN_CASES} cases or more."
        )
    elif confirming:
        verdict = Verdict.CONFIRMED
        best = max(confirming, key=lambda r: r.fix_ci[0])
        rationale = (
            f"{best.intervention_id} fixed {best.fixed} of {best.n_cases} cases with "
            f"{best.regressions} regressions in {best.n_control} control cases."
        )
    elif options:
        verdict = Verdict.SUPPORTED
        best = max(results, key=lambda r: r.fix_ci[0])
        why = []
        if best.fix_ci[0] < MIN_FIX_LO:
            why.append(f"the lower limit of its fix rate is {best.fix_ci[0]:.0%}")
        if best.regression_ci[1] > MAX_REGRESSION_HI:
            why.append(
                f"the maximum limit of its regression rate is {best.regression_ci[1]:.0%} "
                f"with {best.n_control} control cases"
            )
        rationale = (
            f"The classifier found evidence. The best intervention is "
            f"{best.intervention_id}, but " + " and ".join(why) + "."
        )
    else:
        verdict = Verdict.SUPPORTED
        rationale = "The classifier found evidence. The playbook has no intervention for it."
    deployable = [r for r in confirming if r.deployable]
    recommended = (
        max(deployable, key=lambda r: (r.fix_ci[0], -r.regressions)).intervention_id
        if deployable
        else None
    )
    return ClusterDiagnosis(
        cluster=cluster,
        hypotheses=tuple(i.description for i in options),
        results=results,
        verdict=verdict,
        confirmed_by=max(confirming, key=lambda r: r.fix_ci[0]).intervention_id
        if confirming
        else None,
        recommended_fix=recommended,
        rationale=rationale,
    )


def diagnose_run(
    tenant: Tenant,
    run: RunResult,
    dataset: Dataset,
    llm: LLMClient,
    allow_test: bool = False,
    max_control: int = 20,
    max_clusters: int = 8,
) -> Diagnosis:
    if dataset.content_hash != run.dataset_hash:
        raise ConfigError(f"dataset {dataset.ref} is not the dataset of run {run.run_id}")
    warnings: list[str] = []
    if run.dataset_split != "dev":
        if not allow_test:
            raise ConfigError(
                "interventions tune the agent. Use a run on the dev split, or set "
                "allow_test to accept the risk."
            )
        warnings.append(
            "This diagnosis used the test split. Do not use the test split again "
            "for a release gate."
        )
    if run.provenance == Provenance.PIPELINE_TEST:
        warnings.append("The run used a stand-in model. The diagnosis tests the pipeline only.")
    labels = classify_run(run, tenant.pack.knowledge_rules)
    clusters = cluster_failures(labels, run)
    control = _control_ids(run, max_control)
    diagnosed = tuple(
        _diagnose_cluster(tenant, run, dataset, c, llm, control) for c in clusters[:max_clusters]
    )
    if len(clusters) > max_clusters:
        warnings.append(f"Only the {max_clusters} largest clusters have interventions.")
    return Diagnosis(
        run_id=run.run_id,
        tenant_id=run.tenant_id,
        agent_config_id=run.agent_config.id,
        dataset_ref=run.dataset_ref,
        split=run.dataset_split,
        provenance=run.provenance,
        n_trials=len(run.results),
        n_failures=len(labels),
        labels=tuple(labels),
        clusters=diagnosed,
        warnings=tuple(warnings),
    )
