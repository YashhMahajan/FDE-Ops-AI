from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import field_validator

from fdeops.core.config import load_model
from fdeops.core.hashing import content_hash
from fdeops.core.ids import stable_id
from fdeops.core.model import FrozenModel
from fdeops.eval.runner import RunResult
from fdeops.tenancy.loader import Tenant


class _Gate(FrozenModel):
    why: str

    @field_validator("why")
    @classmethod
    def _explained(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("each gate must explain why it exists")
        return v


class TaskSuccessGate(_Gate):
    min_lower_limit: float


class CriticalGate(_Gate):
    max_trials: int = 0
    max_upper_limit: float


class NonInferiorityGate(_Gate):
    margin: float
    slices: tuple[str, ...]


class LatencyGate(_Gate):
    max_p95_ms: float


class CostGate(_Gate):
    max_usd_per_resolution: float
    allow_unmeasured: bool = False


class RequiredGate(_Gate):
    required: bool = True


class KappaGate(_Gate):
    min_kappa: float


class Pricing(FrozenModel):
    usd_per_mtok_input: float
    usd_per_mtok_output: float
    basis: str


class GateConfig(FrozenModel):
    task_success: TaskSuccessGate | None = None
    critical_violations: CriticalGate | None = None
    non_inferiority: NonInferiorityGate | None = None
    latency: LatencyGate | None = None
    cost: CostGate | None = None
    integration_suite: RequiredGate | None = None
    regression_suite: RequiredGate | None = None
    judge_calibration: KappaGate | None = None
    pii_redaction: RequiredGate | None = None
    approver_roles: tuple[str, ...]
    pricing: Pricing | None = None

    def gates(self) -> dict[str, _Gate]:
        names = (
            "task_success",
            "critical_violations",
            "non_inferiority",
            "latency",
            "cost",
            "integration_suite",
            "regression_suite",
            "judge_calibration",
            "pii_redaction",
        )
        return {n: g for n in names if (g := getattr(self, n)) is not None}

    @property
    def content_hash(self) -> str:
        return content_hash(self)


def load_gates(path: Path) -> GateConfig:
    return load_model(path, GateConfig)


GateStatus = Literal["pass", "fail", "not_measured", "not_applicable"]


class GateResult(FrozenModel):
    gate: str
    status: GateStatus
    passed: bool
    observed: str
    threshold: str
    why: str


class Release(FrozenModel):
    """An immutable bundle: model, prompt, retrieval, tools (in the config), KB, dataset, gates."""

    release_id: str
    tenant_id: str
    version: str
    agent_config_id: str
    agent_config: dict[str, object]
    agent_config_hash: str
    kb_hash: str
    gate_dataset_hash: str
    gates_hash: str
    bundle_hash: str

    @classmethod
    def from_run(cls, tenant: Tenant, gates: GateConfig, run: RunResult, version: str) -> "Release":
        parts = {
            "tenant_id": tenant.id,
            "agent_config_hash": run.agent_config_hash,
            "kb_hash": tenant.kb.content_hash,
            "gate_dataset_hash": run.dataset_hash,
            "gates_hash": gates.content_hash,
        }
        bundle = content_hash(parts)
        return cls(
            release_id=stable_id("rel", bundle, version),
            version=version,
            agent_config_id=run.agent_config.id,
            agent_config=run.agent_config.model_dump(mode="json"),
            bundle_hash=bundle,
            **parts,
        )


class ApprovalRecord(FrozenModel):
    approver: str
    role: str
    decision: Literal["approve", "reject"]
    comment: str
    at: datetime


DecisionStatus = Literal["pending_approval", "approved", "rejected", "rejected_by_gates"]


class ReleaseDecision(FrozenModel):
    decision_id: str
    tenant_id: str
    release: Release
    candidate_run_id: str
    baseline_run_id: str | None
    gates: tuple[GateResult, ...]
    gates_passed: bool
    status: DecisionStatus
    approval: ApprovalRecord | None = None
    created_at: datetime
    notes: str = ""
    regression_cases: tuple[str, ...] = ()
    """Cases that the approval adds to the regression suite (for example, the incident cases)."""


class HistoryEvent(FrozenModel):
    action: Literal["approve", "reject", "rollback"]
    release_id: str
    version: str
    actor: str
    role: str
    at: datetime
    detail: str = ""
