"""The improvement loop. It stops at a decision that waits for a person.

1. Diagnose the failures of a dev run and take the largest cluster with a recommended fix.
2. Make a candidate configuration with the fix.
3. Experiment on the dev split: the candidate must be better, and no case can become worse.
4. Run the candidate on the test split, and run the integration and regression suites.
5. Evaluate the gates against the production baseline and propose a release.

The loop never reads the test split to select a fix, and it never moves production.
"""

from pathlib import Path
from typing import Any, Literal

from fdeops.agent.config import apply_patch
from fdeops.core.errors import ConfigError
from fdeops.core.ids import new_id
from fdeops.core.model import FrozenModel
from fdeops.diagnose.interventions import PLAYBOOK, diagnose_run
from fdeops.diagnose.report import save_diagnosis
from fdeops.eval.compare import compare_runs
from fdeops.eval.report import save_run
from fdeops.eval.runner import RunResult, run_eval
from fdeops.llm.types import LLMClient
from fdeops.release.gates import evaluate_gates
from fdeops.release.integration import run_integration_suite
from fdeops.release.models import GateConfig, Release
from fdeops.release.registry import ReleaseRegistry
from fdeops.tenancy.loader import Tenant
from fdeops.world.dataset import Dataset

Status = Literal["no_fix", "rejected_in_experiment", "rejected_by_gates", "pending_approval"]


class ImprovementResult(FrozenModel):
    proposal_id: str
    tenant_id: str
    status: Status
    diagnosis_run_id: str
    cluster_id: str | None = None
    intervention_id: str | None = None
    patch: dict[str, Any] = {}
    candidate_config_id: str | None = None
    dev_run_id: str | None = None
    dev_experiment: dict[str, float] | None = None
    gate_run_id: str | None = None
    baseline_run_id: str | None = None
    integration_passed: bool | None = None
    regression_passed: bool | None = None
    decision_id: str | None = None
    regression_cases: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


def _subset(ds: Dataset, ids: set[str]) -> Dataset:
    return ds.model_copy(update={"cases": tuple(c for c in ds.cases if c.id in ids)})


def improve(
    tenant: Tenant,
    gates: GateConfig,
    registry: ReleaseRegistry,
    dev_run: RunResult,
    dev: Dataset,
    test: Dataset,
    baseline_test_run: RunResult,
    llm: LLMClient,
    version: str,
    runs_dir: Path | None = None,
) -> ImprovementResult:
    if dev_run.dataset_split != "dev" or dev.split != "dev" or test.split != "test":
        raise ConfigError(
            "the improvement loop selects fixes on the dev split and gates on the test split"
        )
    pid = new_id("imp")
    base: dict[str, Any] = {
        "proposal_id": pid,
        "tenant_id": tenant.id,
        "diagnosis_run_id": dev_run.run_id,
    }
    diagnosis = diagnose_run(tenant, dev_run, dev, llm)
    if runs_dir is not None:
        save_diagnosis(diagnosis, save_run(dev_run, runs_dir))
    target = next((c for c in diagnosis.clusters if c.recommended_fix), None)
    if target is None:
        return ImprovementResult(
            **base, status="no_fix", notes=("No cluster has a confirmed, deployable fix.",)
        )
    intervention = next(i for i in PLAYBOOK if i.id == target.recommended_fix)
    candidate = apply_patch(dev_run.agent_config, intervention.patch).model_copy(
        update={"id": f"{dev_run.agent_config.id}+{intervention.id}"}
    )
    common = {
        **base,
        "cluster_id": target.cluster.id,
        "intervention_id": intervention.id,
        "patch": intervention.patch,
        "candidate_config_id": candidate.id,
    }

    def _run(ds: Dataset) -> RunResult:
        r = run_eval(
            tenant,
            candidate,
            ds,
            llm,
            trials=dev_run.trials,
            faults=dev_run.faults,
            llm_mode=dev_run.llm_mode,
            llm_settings=dev_run.llm_settings,
        )
        if runs_dir is not None:
            save_run(r, runs_dir)
        return r

    cand_dev = _run(dev)
    cmp = compare_runs(dev_run, cand_dev)
    experiment = {
        "diff_mean": cmp.diff.mean,
        "diff_lo": cmp.diff.lo,
        "diff_hi": cmp.diff.hi,
        "p": cmp.mcnemar_p,
        "worse_cases": float(cmp.a_only),
    }
    if cmp.diff.mean <= 0 or cmp.a_only > 0:
        return ImprovementResult(
            **common,
            status="rejected_in_experiment",
            dev_run_id=cand_dev.run_id,
            dev_experiment=experiment,
            notes=(
                f"On dev, {cmp.a_only} case(s) became worse, and the mean "
                f"difference is {cmp.diff.mean:+.3f}.",
            ),
        )
    cand_test = _run(test)
    integration = run_integration_suite(tenant, candidate, dev, llm, sample=16)
    regression_ids = set(registry.regression_cases()) | set(target.cluster.case_ids)
    reg_run = _run(_subset(dev, regression_ids)) if regression_ids else None
    regression_ok = reg_run is None or all(r.success for r in reg_run.results)
    results = evaluate_gates(
        tenant,
        gates,
        cand_test,
        baseline=baseline_test_run,
        integration_passed=integration.passed,
        regression_passed=regression_ok,
    )
    evidence = (
        f"Diagnosis of `{dev_run.run_id}` found cluster `{target.cluster.id}` "
        f"({target.verdict.value}). The fix `{intervention.id}` changed the dev success by "
        f"{cmp.diff.mean:+.3f} (95% CI {cmp.diff.lo:+.3f} to {cmp.diff.hi:+.3f}), and no "
        f"case became worse."
    )
    decision = registry.propose(
        Release.from_run(tenant, gates, cand_test, version),
        cand_test.run_id,
        baseline_test_run.run_id,
        results,
        notes=evidence,
        regression_cases=tuple(sorted(regression_ids)),
    )
    return ImprovementResult(
        **common,
        status=decision.status if decision.status != "approved" else "pending_approval",
        dev_run_id=cand_dev.run_id,
        dev_experiment=experiment,
        gate_run_id=cand_test.run_id,
        baseline_run_id=baseline_test_run.run_id,
        integration_passed=integration.passed,
        regression_passed=regression_ok,
        decision_id=decision.decision_id,
        regression_cases=decision.regression_cases,
        notes=(evidence, *(f"gate {g.gate}: {g.status}" for g in results if not g.passed)),
    )
