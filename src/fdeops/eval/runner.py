"""Run a dataset through an agent configuration: cases × trials → scored trial results."""

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from fdeops import __version__
from fdeops.agent.config import AgentConfig
from fdeops.agent.episode import EpisodeResult, run_episode
from fdeops.connectors.faults import FaultRule
from fdeops.core.clock import Clock, SystemClock
from fdeops.core.errors import ConfigError
from fdeops.core.hashing import content_hash
from fdeops.core.ids import new_id
from fdeops.core.model import FrozenModel
from fdeops.core.provenance import Provenance
from fdeops.eval.evaluators import DEFAULT_EVALUATORS, trial_success
from fdeops.eval.types import EvalContext, Evaluator, Score
from fdeops.llm.types import LLMClient
from fdeops.retrieval.retriever import Retriever
from fdeops.tenancy.loader import Tenant
from fdeops.world.cases import Case
from fdeops.world.dataset import Dataset

STAND_IN_PROVIDERS = frozenset({"scripted", "heuristic"})


class TrialResult(FrozenModel):
    case_id: str
    scenario: str
    tags: tuple[str, ...]
    difficulty: str
    trial: int
    success: bool
    scores: tuple[Score, ...]
    episode: EpisodeResult

    def score(self, name: str) -> Score | None:
        return next((s for s in self.scores if s.name == name), None)


class RunResult(FrozenModel):
    run_id: str
    fdeops_version: str
    tenant_id: str
    agent_config: AgentConfig
    agent_config_hash: str
    dataset_ref: str
    dataset_split: str
    dataset_hash: str
    trials: int
    llm_provider: str
    llm_mode: str
    provenance: Provenance
    faults: tuple[FaultRule, ...]
    started_at: datetime
    finished_at: datetime
    results: tuple[TrialResult, ...]


def check_dataset(tenant: Tenant, dataset: Dataset) -> None:
    """A dataset is only valid against the world and knowledge base it was generated from."""
    if dataset.tenant_id != tenant.id:
        raise ConfigError(f"dataset {dataset.ref} belongs to tenant {dataset.tenant_id!r}")
    if dataset.kb_hash != tenant.kb.content_hash:
        raise ConfigError(
            f"dataset {dataset.ref} was built from a different knowledge base; "
            "rebuild it or check out the matching tenant config"
        )
    if dataset.world_hash != content_hash(tenant.base_world):
        raise ConfigError(f"dataset {dataset.ref} was built from a different base world")


def run_eval(
    tenant: Tenant,
    config: AgentConfig,
    dataset: Dataset,
    llm: LLMClient,
    trials: int = 1,
    evaluators: Sequence[Evaluator] = DEFAULT_EVALUATORS,
    max_workers: int = 4,
    faults: Sequence[FaultRule] = (),
    llm_mode: str = "live",
    clock: Clock | None = None,
) -> RunResult:
    check_dataset(tenant, dataset)
    clock = clock or SystemClock()
    started = clock.now()
    retriever = Retriever(tenant.kb, config.retrieval)
    ctx = EvalContext(tenant=tenant)

    def one(job: tuple[Case, int]) -> TrialResult:
        case, trial = job
        ep = run_episode(case, tenant, config, llm, trial, faults=faults, retriever=retriever)
        scores = tuple(s for e in evaluators for s in e.evaluate(case, ep, ctx))
        return TrialResult(
            case_id=case.id,
            scenario=case.scenario,
            tags=case.tags,
            difficulty=case.difficulty,
            trial=trial,
            success=trial_success(scores),
            scores=scores,
            episode=ep,
        )

    jobs = [(c, t) for c in dataset.cases for t in range(trials)]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = tuple(pool.map(one, jobs))
    provenance = (
        Provenance.PIPELINE_TEST
        if llm.provider in STAND_IN_PROVIDERS
        else Provenance.MEASURED_IN_SIMULATION
    )
    return RunResult(
        run_id=new_id("run"),
        fdeops_version=__version__,
        tenant_id=tenant.id,
        agent_config=config,
        agent_config_hash=config.content_hash,
        dataset_ref=dataset.ref,
        dataset_split=dataset.split,
        dataset_hash=dataset.content_hash,
        trials=trials,
        llm_provider=llm.provider,
        llm_mode=llm_mode,
        provenance=provenance,
        faults=tuple(faults),
        started_at=started,
        finished_at=clock.now(),
        results=results,
    )
