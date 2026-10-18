"""The FDE-Ops-AI service.

Each route under ``/v1/tenants/{tenant_id}`` goes through the tenant guard. A key for one tenant
gets HTTP 404 for the data of a different tenant: the response does not show if the data is there.
Long work (runs, diagnoses) goes to the job queue, and the response is HTTP 202 with a job ID.
"""

import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, field_validator

from fdeops import __version__
from fdeops.core.errors import ConfigError, FdeOpsError
from fdeops.core.ids import new_id
from fdeops.eval.calibration import calibrate
from fdeops.eval.compare import compare_runs
from fdeops.jobs.handlers import Context
from fdeops.jobs.handlers import handlers as job_handlers
from fdeops.jobs.queue import JobQueue
from fdeops.jobs.worker import Worker
from fdeops.release.memo import render_memo
from fdeops.release.models import load_gates
from fdeops.release.registry import ReleaseRegistry
from fdeops.storage.artifacts import LocalArtifactStore
from fdeops.storage.db import Database
from fdeops.storage.keys import KeyStore, Principal, Role
from fdeops.storage.repo import NotFound, Repository

log = logging.getLogger("fdeops.api")


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {"level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        data.update(getattr(record, "fields", {}))
        return json.dumps(data, default=str)


@dataclass(frozen=True)
class Settings:
    database_url: str
    artifacts_dir: Path
    tenants_dir: Path
    registry_dir: Path
    configs_dir: Path
    cors_origins: tuple[str, ...] = field(default=())

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ
        return cls(
            database_url=e.get("FDEOPS_DATABASE_URL", "sqlite:///fdeops.db"),
            artifacts_dir=Path(e.get("FDEOPS_ARTIFACTS_DIR", "artifacts")),
            tenants_dir=Path(e.get("FDEOPS_TENANTS_DIR", "tenants")),
            registry_dir=Path(e.get("FDEOPS_REGISTRY_DIR", "releases")),
            configs_dir=Path(e.get("FDEOPS_CONFIGS_DIR", "configs")),
            cors_origins=tuple(o for o in e.get("FDEOPS_CORS_ORIGINS", "").split(",") if o),
        )


class RunRequest(BaseModel):
    agent_config: str = Field(description="Path under configs/, for example agents/x.yaml")
    dataset: str = "support-core"
    split: str = "dev"
    trials: int = Field(1, ge=1, le=10)
    limit: int | None = Field(None, ge=1)
    incident: str | None = Field(None, description="Path under incidents/")
    llm_settings: dict[str, Any] = {}

    @field_validator("agent_config", "incident")
    @classmethod
    def _relative(cls, v: str | None) -> str | None:
        if v is not None and (v.startswith("/") or ".." in Path(v).parts):
            raise ValueError("must be a relative path without '..'")
        return v

    @field_validator("split")
    @classmethod
    def _split(cls, v: str) -> str:
        if v not in ("dev", "test"):
            raise ValueError("must be dev or test")
        return v


class AnnotationRequest(BaseModel):
    run_id: str
    case_id: str
    trial: int
    rubric: str
    label: bool


class ApprovalRequest(BaseModel):
    comment: str = ""


class RollbackRequest(BaseModel):
    reason: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    db = Database(settings.database_url)
    db.init()
    artifacts = LocalArtifactStore(settings.artifacts_dir)
    queue = JobQueue(db)
    ctx = Context(
        db=db,
        artifacts=artifacts,
        tenants_dir=settings.tenants_dir,
        configs_dir=settings.configs_dir,
    )
    app = FastAPI(
        title="FDE-Ops-AI",
        version=__version__,
        description="Evaluate, diagnose and release AI agents with evidence.",
    )
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
        log.addHandler(handler)
        log.setLevel(logging.INFO)
    if settings.cors_origins:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def request_log(request: Request, call_next: Callable[..., Any]) -> Response:
        rid = new_id("req")
        start = time.perf_counter()
        response: Response = await call_next(request)
        response.headers["x-request-id"] = rid
        log.info(
            "request",
            extra={
                "fields": {
                    "request_id": rid,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "ms": round((time.perf_counter() - start) * 1000, 1),
                    "principal": getattr(request.state, "principal", None),
                }
            },
        )
        return response

    @app.exception_handler(FdeOpsError)
    async def fdeops_error(request: Request, exc: FdeOpsError) -> JSONResponse:
        status = 404 if isinstance(exc, NotFound) else 422
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    # ------------------------------------------------------------------ auth
    def principal(
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        x_api_key: Annotated[str | None, Header()] = None,
    ) -> Principal:
        secret = x_api_key or (
            authorization.removeprefix("Bearer ").strip() if authorization else None
        )
        if not secret:
            raise HTTPException(401, "an API key is necessary")
        with db.session() as s:
            p = KeyStore(s).authenticate(secret)
        if p is None:
            raise HTTPException(401, "the API key is not valid")
        request.state.principal = p.key_id
        return p

    def guard(minimum: Role) -> Callable[..., Principal]:
        def dep(tenant_id: str, p: Annotated[Principal, Depends(principal)]) -> Principal:
            if not p.can_access(tenant_id) or not (settings.tenants_dir / tenant_id).is_dir():
                raise HTTPException(404, "tenant not found")
            if not p.role.allows(minimum):
                raise HTTPException(403, f"this needs the {minimum.value} role")
            return p

        return dep

    Viewer = Annotated[Principal, Depends(guard(Role.VIEWER))]
    Engineer = Annotated[Principal, Depends(guard(Role.ENGINEER))]
    Approver = Annotated[Principal, Depends(guard(Role.APPROVER))]

    def admin(p: Annotated[Principal, Depends(principal)]) -> Principal:
        if p.role != Role.ADMIN:
            raise HTTPException(403, "this needs the admin role")
        return p

    def repo_for(tenant_id: str) -> Any:
        return db.session(), tenant_id

    # ------------------------------------------------------------------ routes
    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/v1/tenants")
    def tenants(p: Annotated[Principal, Depends(principal)]) -> list[dict[str, Any]]:
        out = []
        for d in sorted(settings.tenants_dir.iterdir()):
            if (d / "tenant.yaml").exists() and p.can_access(d.name):
                t = ctx.tenant(d.name)
                out.append(
                    {
                        "id": t.id,
                        "display_name": t.config.display_name,
                        "pack": t.pack.id,
                        "notes": t.config.notes,
                    }
                )
        return out

    @app.get("/v1/tenants/{tenant_id}")
    def tenant(tenant_id: str, p: Viewer) -> dict[str, Any]:
        t = ctx.tenant(tenant_id)
        q = t.data_quality
        return {
            "id": t.id,
            "display_name": t.config.display_name,
            "pack": t.pack.id,
            "kb_sections": len(t.kb.keys()),
            "scenarios": sorted(t.pack.scenarios()),
            "datasets": [d.model_dump(mode="json") for d in t.config.datasets],
            "pii_redaction": t.config.pii.redact,
            "data_quality": {
                "loaded": q.loaded,
                "quarantined": q.quarantined,
                "issues": len(q.issues),
            },
        }

    @app.post("/v1/tenants/{tenant_id}/runs", status_code=202)
    def start_run(tenant_id: str, body: RunRequest, p: Engineer) -> dict[str, str]:
        job_id = queue.enqueue(tenant_id, "eval_run", body.model_dump())
        with db.session() as s:
            Repository(s, tenant_id, artifacts).audit(
                p.name, "run.requested", job_id, body.model_dump_json()
            )
        return {"job_id": job_id}

    @app.get("/v1/tenants/{tenant_id}/jobs/{job_id}")
    def job(tenant_id: str, job_id: str, p: Viewer) -> dict[str, Any]:
        try:
            return queue.get(job_id, tenant_id).model_dump()
        except ConfigError as e:
            raise HTTPException(404, "job not found") from e

    @app.get("/v1/tenants/{tenant_id}/runs")
    def runs(tenant_id: str, p: Viewer) -> list[dict[str, Any]]:
        with db.session() as s:
            rows = Repository(s, tenant_id, artifacts).list_runs()
            return [
                {
                    "run_id": r.run_id,
                    "agent_config_id": r.agent_config_id,
                    "dataset_ref": r.dataset_ref,
                    "split": r.split,
                    "provenance": r.provenance,
                    "success_rate": r.success_rate,
                    "n_trials": r.n_trials,
                    "incident_id": r.incident_id,
                    "started_at": r.started_at.isoformat(),
                }
                for r in rows
            ]

    @app.get("/v1/tenants/{tenant_id}/runs/{run_id}")
    def run_summary(tenant_id: str, run_id: str, p: Viewer) -> Response:
        with db.session() as s:
            row = Repository(s, tenant_id, artifacts).run_row(run_id)
        return Response(
            artifacts.get_text(row.artifact_uri.replace("run.json", "summary.json")),
            media_type="application/json",
        )

    @app.get("/v1/tenants/{tenant_id}/runs/{run_id}/report")
    def run_report(tenant_id: str, run_id: str, p: Viewer) -> PlainTextResponse:
        with db.session() as s:
            return PlainTextResponse(
                Repository(s, tenant_id, artifacts).report(run_id), media_type="text/markdown"
            )

    @app.get("/v1/tenants/{tenant_id}/runs/{run_id}/trials")
    def trials(tenant_id: str, run_id: str, p: Viewer) -> list[dict[str, Any]]:
        with db.session() as s:
            return [
                {
                    "case_id": t.case_id,
                    "trial": t.trial,
                    "scenario": t.scenario,
                    "tags": t.tags,
                    "success": t.success,
                    "primary_failure": t.primary_failure,
                }
                for t in Repository(s, tenant_id, artifacts).trials(run_id)
            ]

    @app.get("/v1/tenants/{tenant_id}/runs/{run_id}/trials/{case_id}/{trial}")
    def trial_detail(
        tenant_id: str, run_id: str, case_id: str, trial: int, p: Viewer
    ) -> dict[str, Any]:
        with db.session() as s:
            run = Repository(s, tenant_id, artifacts).load_run(run_id)
        r = next((x for x in run.results if x.case_id == case_id and x.trial == trial), None)
        if r is None:
            raise HTTPException(404, "trial not found")
        return r.model_dump(mode="json")

    @app.post("/v1/tenants/{tenant_id}/runs/{run_id}/diagnose", status_code=202)
    def start_diagnose(
        tenant_id: str, run_id: str, p: Engineer, allow_test: bool = False
    ) -> dict[str, str]:
        with db.session() as s:
            repo = Repository(s, tenant_id, artifacts)
            repo.run_row(run_id)
            repo.audit(p.name, "diagnose.requested", run_id)
        return {
            "job_id": queue.enqueue(
                tenant_id, "diagnose", {"run_id": run_id, "allow_test": allow_test}
            )
        }

    @app.get("/v1/tenants/{tenant_id}/runs/{run_id}/diagnosis")
    def diagnosis(tenant_id: str, run_id: str, p: Viewer) -> Response:
        with db.session() as s:
            Repository(s, tenant_id, artifacts).run_row(run_id)
        key = f"runs/{tenant_id}/{run_id}/diagnosis.json"
        if not artifacts.exists(key):
            raise HTTPException(404, "no diagnosis for this run")
        return Response(artifacts.get_text(key), media_type="application/json")

    @app.get("/v1/tenants/{tenant_id}/compare")
    def compare(tenant_id: str, a: str, b: str, p: Viewer) -> dict[str, Any]:
        with db.session() as s:
            repo = Repository(s, tenant_id, artifacts)
            return compare_runs(repo.load_run(a), repo.load_run(b)).model_dump(mode="json")

    @app.post("/v1/tenants/{tenant_id}/annotations", status_code=201)
    def annotate(tenant_id: str, body: AnnotationRequest, p: Engineer) -> dict[str, Any]:
        with db.session() as s:
            row = Repository(s, tenant_id, artifacts).annotate(
                body.run_id, body.case_id, body.trial, body.rubric, body.label, p.name
            )
            return {"id": row.id}

    @app.get("/v1/tenants/{tenant_id}/runs/{run_id}/calibration")
    def calibration(tenant_id: str, run_id: str, rubric: str, p: Viewer) -> dict[str, Any]:
        with db.session() as s:
            repo = Repository(s, tenant_id, artifacts)
            run = repo.load_run(run_id)
            human = repo.human_labels(run_id, rubric)
        name = rubric if rubric == "outcome" else f"judge.{rubric}"
        auto = {
            f"{r.case_id}:{r.trial}": bool(sc.passed)
            for r in run.results
            if (sc := r.score(name)) is not None and sc.passed is not None
        }
        return calibrate(name, auto, human).model_dump(mode="json")

    @app.get("/v1/tenants/{tenant_id}/audit")
    def audit(tenant_id: str, p: Approver) -> list[dict[str, Any]]:
        with db.session() as s:
            return [
                {
                    "actor": e.actor,
                    "action": e.action,
                    "target": e.target,
                    "detail": e.detail,
                    "at": e.at.isoformat(),
                }
                for e in Repository(s, tenant_id, artifacts).audit_events()
            ]

    def registry(tenant_id: str) -> ReleaseRegistry:
        return ReleaseRegistry(settings.registry_dir, tenant_id)

    @app.get("/v1/tenants/{tenant_id}/releases")
    def releases(tenant_id: str, p: Viewer) -> dict[str, Any]:
        reg = registry(tenant_id)
        prod = reg.production()
        return {
            "production": prod.model_dump(mode="json") if prod else None,
            "decisions": [d.model_dump(mode="json") for d in reg.decisions()],
            "history": [e.model_dump(mode="json") for e in reg.history()],
        }

    @app.get("/v1/tenants/{tenant_id}/releases/{decision_id}/memo")
    def memo(tenant_id: str, decision_id: str, p: Viewer) -> PlainTextResponse:
        return PlainTextResponse(
            render_memo(registry(tenant_id).decision(decision_id)), media_type="text/markdown"
        )

    @app.post("/v1/tenants/{tenant_id}/releases/{decision_id}/approve")
    def approve(
        tenant_id: str, decision_id: str, body: ApprovalRequest, p: Approver
    ) -> dict[str, Any]:
        gates = load_gates(settings.tenants_dir / tenant_id / "gates.yaml")
        d = registry(tenant_id).approve(
            decision_id, p.name, p.role.value, body.comment, (*gates.approver_roles, "admin")
        )
        with db.session() as s:
            Repository(s, tenant_id, artifacts).audit(
                p.name, "release.approved", decision_id, body.comment
            )
        return d.model_dump(mode="json")

    @app.post("/v1/tenants/{tenant_id}/releases/rollback")
    def rollback(tenant_id: str, body: RollbackRequest, p: Approver) -> dict[str, Any]:
        gates = load_gates(settings.tenants_dir / tenant_id / "gates.yaml")
        current = registry(tenant_id).rollback(
            p.name, p.role.value, body.reason, (*gates.approver_roles, "admin")
        )
        with db.session() as s:
            Repository(s, tenant_id, artifacts).audit(
                p.name, "release.rollback", current.release_id, body.reason
            )
        return current.model_dump(mode="json")

    @app.post("/v1/admin/worker/run-once")
    def worker_once(p: Annotated[Principal, Depends(admin)]) -> dict[str, bool]:
        """Run one job in the API process. Deployments use ``fdeops worker`` instead."""
        return {"ran": Worker(queue, job_handlers(ctx), name="api").run_once()}

    app.state.settings = settings
    app.state.db = db
    return app
