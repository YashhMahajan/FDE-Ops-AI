"""Shadow mode: run a candidate on the same traffic as production, with no effect on production.

Each episode uses its own copy of the world, thus the candidate cannot change production data.
The report shows where the two configurations disagree. It is evidence for a release decision,
not a gate.
"""

from fdeops.agent.config import AgentConfig
from fdeops.core.model import FrozenModel
from fdeops.eval.runner import RunResult, run_eval
from fdeops.llm.types import LLMClient
from fdeops.tenancy.loader import Tenant
from fdeops.world.dataset import Dataset


class Disagreement(FrozenModel):
    case_id: str
    scenario: str
    production_success: bool
    candidate_success: bool
    production_resolution: str | None
    candidate_resolution: str | None


class ShadowReport(FrozenModel):
    tenant_id: str
    production_run_id: str
    candidate_run_id: str
    n_cases: int
    agreement: float
    production_success: float
    candidate_success: float
    disagreements: tuple[Disagreement, ...]


def _resolution(run: RunResult, case_id: str) -> tuple[bool, str | None]:
    r = next(x for x in run.results if x.case_id == case_id and x.trial == 0)
    out = r.score("outcome")
    return r.success, (str(out.details.get("derived_resolution")) if out else None)


def shadow_compare(
    tenant: Tenant,
    traffic: Dataset,
    production: AgentConfig,
    candidate: AgentConfig,
    llm: LLMClient,
    candidate_llm: LLMClient | None = None,
) -> ShadowReport:
    prod = run_eval(tenant, production, traffic, llm)
    cand = run_eval(tenant, candidate, traffic, candidate_llm or llm)
    disagreements = []
    for c in traffic.cases:
        ps, pr = _resolution(prod, c.id)
        cs, cr = _resolution(cand, c.id)
        if ps != cs or pr != cr:
            disagreements.append(
                Disagreement(
                    case_id=c.id,
                    scenario=c.scenario,
                    production_success=ps,
                    candidate_success=cs,
                    production_resolution=pr,
                    candidate_resolution=cr,
                )
            )
    n = len(traffic.cases)
    return ShadowReport(
        tenant_id=tenant.id,
        production_run_id=prod.run_id,
        candidate_run_id=cand.run_id,
        n_cases=n,
        agreement=1 - len(disagreements) / n if n else 1.0,
        production_success=sum(r.success for r in prod.results) / len(prod.results),
        candidate_success=sum(r.success for r in cand.results) / len(cand.results),
        disagreements=tuple(disagreements),
    )
