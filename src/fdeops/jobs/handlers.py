"""Job handlers: the work that the API puts in the queue and a worker does."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from fdeops.agent.config import load_agent_config
from fdeops.core.errors import ConfigError
from fdeops.diagnose.interventions import diagnose_run
from fdeops.diagnose.report import render_diagnosis
from fdeops.eval.incidents import load_incident
from fdeops.eval.runner import run_eval
from fdeops.llm.presets import PRESETS, build_provider
from fdeops.llm.retrying import RetryingLLM
from fdeops.llm.types import LLMClient
from fdeops.storage.artifacts import LocalArtifactStore
from fdeops.storage.db import Database
from fdeops.storage.repo import Repository
from fdeops.tenancy.loader import Tenant, load_tenant


@dataclass(frozen=True)
class Context:
    db: Database
    artifacts: LocalArtifactStore
    tenants_dir: Path
    configs_dir: Path

    def tenant(self, tenant_id: str) -> Tenant:
        return _load_tenant(self.tenants_dir / tenant_id)


@lru_cache(maxsize=16)
def _load_tenant(root: Path) -> Tenant:
    return load_tenant(root)


def safe_path(base: Path, relative: str) -> Path:
    p = (base / relative).resolve()
    if base.resolve() not in p.parents or not p.exists():
        raise ConfigError(f"{relative!r} is not a file in {base.name}/")
    return p


def _llm(tenant: Tenant, provider: str, model: str, settings: dict[str, Any]) -> LLMClient:
    if provider == "heuristic":
        return tenant.pack.heuristic_model(0, settings.get("error_rates", {}))
    if provider in PRESETS:
        return RetryingLLM(build_provider(provider, model))
    raise ConfigError(f"provider {provider!r} cannot run in a job")


def eval_run(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    tenant = ctx.tenant(payload["_tenant_id"])
    config = load_agent_config(safe_path(ctx.configs_dir, payload["agent_config"]))
    dataset = tenant.build_datasets(payload["dataset"])[payload["split"]]
    if payload.get("limit"):
        dataset = dataset.model_copy(update={"cases": dataset.cases[: int(payload["limit"])]})
    incident = (
        load_incident(safe_path(ctx.tenants_dir.parent / "incidents", payload["incident"]))
        if payload.get("incident")
        else None
    )
    settings = payload.get("llm_settings") or {}
    llm = _llm(tenant, config.model.provider, config.model.name, settings)
    run = run_eval(
        tenant,
        config,
        dataset,
        llm,
        trials=int(payload.get("trials", 1)),
        llm_settings=settings,
        incident=incident,
    )
    with ctx.db.session() as s:
        Repository(s, tenant.id, ctx.artifacts).save_run(run)
    return {"run_id": run.run_id}


def diagnose(ctx: Context, payload: dict[str, Any]) -> dict[str, Any]:
    tenant = ctx.tenant(payload["_tenant_id"])
    with ctx.db.session() as s:
        run = Repository(s, tenant.id, ctx.artifacts).load_run(payload["run_id"])
    name = run.dataset_ref.split("/")[1].split("@")[0]
    full = tenant.build_datasets(name)[run.dataset_split]
    ids = {r.case_id for r in run.results}
    dataset = full.model_copy(update={"cases": tuple(c for c in full.cases if c.id in ids)})
    llm = _llm(tenant, run.llm_provider, run.agent_config.model.name, run.llm_settings)
    result = diagnose_run(tenant, run, dataset, llm, allow_test=bool(payload.get("allow_test")))
    base = f"runs/{tenant.id}/{run.run_id}"
    ctx.artifacts.put_text(f"{base}/diagnosis.json", result.model_dump_json(indent=2))
    ctx.artifacts.put_text(f"{base}/diagnosis.md", render_diagnosis(result))
    return {"run_id": run.run_id, "clusters": [c.cluster.id for c in result.clusters]}


def handlers(ctx: Context) -> dict[str, Any]:
    return {"eval_run": lambda p: eval_run(ctx, p), "diagnose": lambda p: diagnose(ctx, p)}
