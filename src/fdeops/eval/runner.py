"""Run a dataset through an agent configuration: cases × trials → scored trial results."""

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from fdeops import __version__
from fdeops.agent.config import AgentConfig
from fdeops.agent.episode import EpisodeResult, ExternalAgent, run_episode, run_external_episode
from fdeops.connectors.faults import FaultRule
from fdeops.core.clock import Clock, SystemClock
from fdeops.core.errors import ConfigError, InvariantError
from fdeops.core.hashing import content_hash
from fdeops.core.ids import new_id
from fdeops.core.model import FrozenModel
from fdeops.core.provenance import Provenance
from fdeops.eval.evaluators import DEFAULT_EVALUATORS, trial_success
from fdeops.eval.incidents import IncidentSpec, apply_incident
from fdeops.eval.types import EvalContext, Evaluator, Score
from fdeops.llm.types import LLMClient
from fdeops.retrieval.retriever import Retriever
from fdeops.tenancy.loader import Tenant
from fdeops.trace.redact import redact_value
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
    llm_settings: dict[str, Any] = {}
    """How to build the same model again (for example, heuristic error rates). Diagnosis uses it."""
    provenance: Provenance
    faults: tuple[FaultRule, ...]
    incident: IncidentSpec | None = None
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
    llm: LLMClient | None,
    trials: int = 1,
    evaluators: Sequence[Evaluator] = DEFAULT_EVALUATORS,
    max_workers: int = 4,
    faults: Sequence[FaultRule] = (),
    llm_mode: str = "live",
    clock: Clock | None = None,
    llm_settings: dict[str, Any] | None = None,
    incident: IncidentSpec | None = None,
    external_agent: ExternalAgent | None = None,
) -> RunResult:
    """Evaluate ``config`` with ``llm`` (the reference agent) or with ``external_agent``."""
    if (llm is None) == (external_agent is None):
        raise ConfigError("give exactly one of llm and external_agent")
    check_dataset(tenant, dataset)
    base_hash, base_ref = dataset.content_hash, dataset.ref
    settings = dict(llm_settings or {})
    if incident is not None:
        effect = apply_incident(incident, tenant, config, dataset, settings)
        tenant, config, dataset = effect.tenant, effect.config, effect.dataset
        faults = (*faults, *effect.faults)
        if effect.llm_settings != settings and llm is not None and llm.provider == "heuristic":
            llm = tenant.pack.heuristic_model(0, effect.llm_settings.get("error_rates", {}))
        settings = effect.llm_settings
    clock = clock or SystemClock()
    started = clock.now()
    retriever = Retriever(tenant.kb, config.retrieval)
    ctx = EvalContext(tenant=tenant)

    def one(job: tuple[Case, int]) -> TrialResult:
        case, trial = job
        if external_agent is not None:
            ep = run_external_episode(
                case, tenant, config, external_agent, trial, faults=faults, retriever=retriever
            )
        else:
            if llm is None:
                raise InvariantError("llm must be set here")
            ep = run_episode(case, tenant, config, llm, trial, faults=faults, retriever=retriever)
        scores = tuple(s for e in evaluators for s in e.evaluate(case, ep, ctx))
        pii = tenant.config.pii
        if pii.redact:  # after scoring: scores use the real text, the stored record does not
            ep = EpisodeResult.model_validate(redact_value(ep.model_dump(mode="json"), pii))
            scores = tuple(
                Score.model_validate(redact_value(s.model_dump(mode="json"), pii)) for s in scores
            )
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
    provider = (
        f"external:{getattr(external_agent, '__name__', 'agent')}"
        if external_agent is not None
        else llm.provider
        if llm is not None
        else "none"
    )
    provenance = (
        Provenance.PIPELINE_TEST
        if provider in STAND_IN_PROVIDERS
        else Provenance.MEASURED_IN_SIMULATION
    )
    return RunResult(
        run_id=new_id("run"),
        fdeops_version=__version__,
        tenant_id=tenant.id,
        agent_config=config,
        agent_config_hash=config.content_hash,
        dataset_ref=base_ref,
        dataset_split=dataset.split,
        dataset_hash=base_hash,
        trials=trials,
        llm_provider=provider,
        llm_mode=llm_mode,
        llm_settings=settings,
        provenance=provenance,
        faults=tuple(faults),
        incident=incident,
        started_at=started,
        finished_at=clock.now(),
        results=results,
    )
