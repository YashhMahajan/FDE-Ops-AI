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

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, text

from fdeops import __version__
from fdeops.api.security import (
    API_ONLY_HEADERS,
    SECURITY_HEADERS,
    TENANT_ID,
    Metrics,
    RateLimiter,
)
from fdeops.core.errors import ConfigError, FdeOpsError
from fdeops.core.ids import new_id
from fdeops.diagnose.interventions import Diagnosis
from fdeops.eval.calibration import calibrate
from fdeops.eval.compare import compare_runs
from fdeops.impact.costs import load_costs
from fdeops.impact.measure import measure_run
from fdeops.impact.report import render_roi
from fdeops.impact.roi import simulate_roi
from fdeops.insights.opportunities import build_opportunities, load_effort
from fdeops.insights.roadmap import render_roadmap
from fdeops.jobs.handlers import Context
from fdeops.jobs.handlers import handlers as job_handlers
from fdeops.jobs.queue import JobQueue
from fdeops.jobs.worker import Worker
from fdeops.release.memo import render_memo
from fdeops.release.models import load_gates
from fdeops.release.registry import ReleaseRegistry
from fdeops.storage.artifacts import LocalArtifactStore
from fdeops.storage.db import Database, JobRow
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
    rate_per_minute: float = 120.0
    """Requests for each API key (or each client address without a key) in one minute."""
    expensive_per_minute: float = 10.0
    """Requests that start work (runs, diagnoses, ROI) for each API key in one minute."""
    auth_failures_per_minute: float = 10.0
    """Requests with a missing or wrong key, for each client address in one minute."""
    max_body_bytes: int = 1_000_000

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
            rate_per_minute=float(e.get("FDEOPS_RATE_PER_MINUTE", "120")),
            expensive_per_minute=float(e.get("FDEOPS_EXPENSIVE_PER_MINUTE", "10")),
            auth_failures_per_minute=float(e.get("FDEOPS_AUTH_FAILURES_PER_MINUTE", "10")),
            max_body_bytes=int(e.get("FDEOPS_MAX_BODY_BYTES", "1000000")),
        )

    def validate(self) -> None:
        """Stop at start-up with a clear message, not at the first request."""
        if not self.tenants_dir.is_dir():
            raise ConfigError("FDEOPS_TENANTS_DIR is not a folder", self.tenants_dir)
        if not self.configs_dir.is_dir():
            raise ConfigError("FDEOPS_CONFIGS_DIR is not a folder", self.configs_dir)
        if "*" in self.cors_origins:
            raise ConfigError("FDEOPS_CORS_ORIGINS must list origins. '*' is not permitted.")
        if min(self.rate_per_minute, self.expensive_per_minute, self.max_body_bytes) <= 0:
            raise ConfigError("rate limits and FDEOPS_MAX_BODY_BYTES must be more than zero")


class LLMSettings(BaseModel):
    """Only the settings that a job can use. An unknown key is an error, not a silent no-op."""

    model_config = ConfigDict(extra="forbid")
    error_rates: dict[str, float] = Field(default_factory=dict, max_length=20)

    @field_validator("error_rates")
    @classmethod
    def _rates(cls, v: dict[str, float]) -> dict[str, float]:
        if any(not 0.0 <= r <= 1.0 for r in v.values()):
            raise ValueError("each error rate must be between 0 and 1")
        return v


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_config: str = Field(
        max_length=200, description="Path under configs/, for example agents/x.yaml"
    )
    dataset: str = Field("support-core", pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")
    split: str = "dev"
    trials: int = Field(1, ge=1, le=10)
    limit: int | None = Field(None, ge=1, le=10_000)
    incident: str | None = Field(None, max_length=200, description="Path under incidents/")
    llm_settings: LLMSettings = Field(default_factory=LLMSettings)

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
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(max_length=64)
    case_id: str = Field(max_length=64)
    trial: int = Field(ge=0, le=100)
    rubric: str = Field(max_length=64)
    label: bool


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment: str = Field("", max_length=2000)


class RollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=2000)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.validate()
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

    metrics = Metrics()
    limiter = RateLimiter(
        per_minute=settings.rate_per_minute, burst=max(10, int(settings.rate_per_minute // 4))
    )
    expensive = RateLimiter(
        per_minute=settings.expensive_per_minute,
        burst=max(2, int(settings.expensive_per_minute // 2)),
    )
    auth_failures = RateLimiter(
        per_minute=settings.auth_failures_per_minute,
        burst=max(3, int(settings.auth_failures_per_minute // 2)),
    )

    def client_address(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    @app.middleware("http")
    async def request_log(request: Request, call_next: Callable[..., Any]) -> Response:
        rid = new_id("req")
        request.state.request_id = rid
        start = time.perf_counter()
        response: Response
        if request.method in ("POST", "PUT", "PATCH"):
            length = request.headers.get("content-length")
            if length is None and request.headers.get("transfer-encoding"):
                response = JSONResponse(
                    status_code=411,
                    content={"detail": "a Content-Length header is necessary", "request_id": rid},
                )
            elif length is not None and (
                not length.isdigit() or int(length) > settings.max_body_bytes
            ):
                response = JSONResponse(
                    status_code=413,
                    content={"detail": "the request body is too large", "request_id": rid},
                )
            else:
                response = await _handle(request, call_next, rid)
        else:
            response = await _handle(request, call_next, rid)
        response.headers["x-request-id"] = rid
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        if request.url.path.startswith("/v1/"):
            for k, v in API_ONLY_HEADERS.items():
                response.headers.setdefault(k, v)
        route = getattr(request.scope.get("route"), "path", "unmatched")
        elapsed = time.perf_counter() - start
        metrics.observe(request.method, route, response.status_code, elapsed)
        log.info(
            "request",
            extra={
                "fields": {
                    "request_id": rid,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "ms": round(elapsed * 1000, 1),
                    "principal": getattr(request.state, "principal", None),
                }
            },
        )
        return response

    async def _handle(request: Request, call_next: Callable[..., Any], rid: str) -> Response:
        try:
            response: Response = await call_next(request)
            return response
        except Exception:  # the client gets a request ID, and the log gets the stack trace
            log.exception("unhandled error", extra={"fields": {"request_id": rid}})
            return JSONResponse(
                status_code=500, content={"detail": "internal error", "request_id": rid}
            )

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
        address = client_address(request)
        if not secret or len(secret) > 200:
            _count_auth_failure(address)
            raise HTTPException(401, "an API key is necessary")
        with db.session() as s:
            p = KeyStore(s).authenticate(secret)
        if p is None:
            _count_auth_failure(address)
            raise HTTPException(401, "the API key is not valid")
        request.state.principal = p.key_id
        allowed, wait = limiter.allow(f"key:{p.key_id}")
        if not allowed:
            raise HTTPException(
                429, "too many requests", headers={"Retry-After": str(max(1, int(wait + 0.999)))}
            )
        path = request.url.path
        starts_work = (request.method == "POST" and path.endswith(("/runs", "/diagnose"))) or (
            path.endswith("/impact")
        )
        if starts_work:
            allowed, wait = expensive.allow(f"key:{p.key_id}")
            if not allowed:
                raise HTTPException(
                    429,
                    "too many requests that start work",
                    headers={"Retry-After": str(max(1, int(wait + 0.999)))},
                )
        return p

    def _count_auth_failure(address: str) -> None:
        allowed, wait = auth_failures.allow(f"ip:{address}")
        if not allowed:
            raise HTTPException(
                429,
                "too many requests without a valid key",
                headers={"Retry-After": str(max(1, int(wait + 0.999)))},
            )

    def guard(minimum: Role) -> Callable[..., Principal]:
        def dep(tenant_id: str, p: Annotated[Principal, Depends(principal)]) -> Principal:
            if (
                not TENANT_ID.fullmatch(tenant_id)
                or not p.can_access(tenant_id)
                or not (settings.tenants_dir / tenant_id).is_dir()
            ):
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
        """Liveness: the process answers. It does not examine dependencies."""
        return {"status": "ok", "version": __version__}

    @app.get("/ready")
    def ready() -> JSONResponse:
        """Readiness: the database answers and the folders are usable. A load balancer uses it."""
        checks: dict[str, bool] = {}
        try:
            with db.session() as s:
                s.execute(text("SELECT 1"))
            checks["database"] = True
        except Exception:  # noqa: BLE001 - any database error means "not ready"
            log.warning("readiness: the database does not answer")
            checks["database"] = False
        checks["tenants"] = settings.tenants_dir.is_dir()
        checks["artifacts"] = settings.artifacts_dir.is_dir() and os.access(
            settings.artifacts_dir, os.W_OK
        )
        ok = all(checks.values())
        return JSONResponse(
            status_code=200 if ok else 503,
            content={"status": "ready" if ok else "not ready", "checks": checks},
        )

    @app.get("/metrics")
    def metrics_endpoint(p: Annotated[Principal, Depends(principal)]) -> PlainTextResponse:
        """Prometheus metrics. It needs an admin key, because route names show the API surface."""
        if p.role != Role.ADMIN:
            raise HTTPException(403, "this needs the admin role")
        with db.session() as s:
            jobs = {
                status: float(n)
                for status, n in s.execute(
                    select(JobRow.status, func.count()).group_by(JobRow.status)
                )
            }
        return PlainTextResponse(
            metrics.render({"fdeops_jobs": jobs}), media_type="text/plain; version=0.0.4"
        )

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
    def runs(
        tenant_id: str,
        p: Viewer,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
    ) -> list[dict[str, Any]]:
        with db.session() as s:
            rows = Repository(s, tenant_id, artifacts).list_runs(limit=limit, offset=offset)
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

    @app.get("/v1/tenants/{tenant_id}/runs/{run_id}/impact")
    def run_impact(
        tenant_id: str,
        run_id: str,
        p: Viewer,
        draws: Annotated[int, Query(ge=100, le=20_000)] = 5000,
    ) -> dict[str, Any]:
        t = ctx.tenant(tenant_id)
        costs = load_costs(t.root / "costs.yaml")
        pricing = load_gates(t.root / "gates.yaml").pricing
        with db.session() as s:
            run = Repository(s, tenant_id, artifacts).load_run(run_id)
        roi = simulate_roi(measure_run(run, costs, pricing), costs, draws=min(draws, 50_000))
        return {**roi.model_dump(mode="json"), "report_md": render_roi(roi)}

    @app.get("/v1/tenants/{tenant_id}/runs/{run_id}/opportunities")
    def run_opportunities(tenant_id: str, run_id: str, p: Viewer) -> dict[str, Any]:
        t = ctx.tenant(tenant_id)
        key = f"runs/{tenant_id}/{run_id}/diagnosis.json"
        with db.session() as s:
            run = Repository(s, tenant_id, artifacts).load_run(run_id)
        if not artifacts.exists(key):
            raise HTTPException(404, "the run has no diagnosis. Start a diagnosis first")
        costs = load_costs(t.root / "costs.yaml")
        opps = build_opportunities(
            run,
            Diagnosis.model_validate_json(artifacts.get_text(key)),
            costs,
            load_effort(t.root / "effort.yaml"),
        )
        return {
            "opportunities": [o.model_dump() for o in opps],
            "roadmap_md": render_roadmap(opps, tenant_id),
        }

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
    def audit(
        tenant_id: str,
        p: Approver,
        limit: Annotated[int, Query(ge=1, le=1000)] = 200,
        offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    ) -> list[dict[str, Any]]:
        with db.session() as s:
            return [
                {
                    "actor": e.actor,
                    "action": e.action,
                    "target": e.target,
                    "detail": e.detail,
                    "at": e.at.isoformat(),
                }
                for e in Repository(s, tenant_id, artifacts).audit_events(
                    limit=limit, offset=offset
                )
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
