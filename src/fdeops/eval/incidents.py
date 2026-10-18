"""Incidents as files. Each incident is one declarative change to a run, with a seed.

A run with an incident uses the same base dataset as its baseline. Thus, a paired comparison of
the baseline run and the incident run is valid, and it shows the effect of the incident.
"""

import dataclasses
import hashlib
import random
from pathlib import Path
from typing import Any, Literal

from fdeops.agent.config import AgentConfig
from fdeops.connectors.faults import FaultRule
from fdeops.core.config import load_model, validate_model
from fdeops.core.errors import ConfigError
from fdeops.core.model import FrozenModel
from fdeops.retrieval.kb import KnowledgeBase
from fdeops.tenancy.loader import Tenant
from fdeops.world.dataset import Dataset

IncidentKind = Literal[
    "api_fault",
    "doc_drift",
    "prompt_injection",
    "model_swap",
    "retrieval_config_change",
    "tool_schema_change",
    "data_quality",
]


class IncidentSpec(FrozenModel):
    id: str
    kind: IncidentKind
    description: str
    tenant: str | None = None
    seed: int = 0
    params: dict[str, Any] = {}


class _FaultParams(FrozenModel):
    rules: list[FaultRule]


class _RetrievalParams(FrozenModel):
    retrieval: dict[str, Any]


class _InjectionParams(FrozenModel):
    target: Literal["ticket", "kb"]
    text: str
    scenarios: list[str] = []
    section: str | None = None


class _ModelSwapParams(FrozenModel):
    model: dict[str, Any] = {}
    llm_settings: dict[str, Any] = {}


class _SchemaParams(FrozenModel):
    op: str
    field: str


class _DataQualityParams(FrozenModel):
    collection: str
    field: str
    modes: dict[Literal["dirty_case", "missing", "blank"], float]


@dataclasses.dataclass(frozen=True)
class IncidentEffect:
    tenant: Tenant
    config: AgentConfig
    dataset: Dataset
    faults: tuple[FaultRule, ...]
    llm_settings: dict[str, Any]


def load_incident(path: Path) -> IncidentSpec:
    return load_model(path, IncidentSpec)


def _patch(config: AgentConfig, patch: dict[str, Any]) -> AgentConfig:
    from fdeops.diagnose.interventions import apply_patch  # one merge rule for all patches

    return apply_patch(config, patch)


def _rng(spec: IncidentSpec, key: str) -> random.Random:
    return random.Random(int(hashlib.sha256(f"{spec.seed}:{key}".encode()).hexdigest()[:12], 16))


def _inject_kb(kb: KnowledgeBase, section: str, text: str) -> KnowledgeBase:
    if section not in kb:
        raise ConfigError(f"incident section {section!r} is not in the knowledge base")
    changed = tuple(
        s.model_copy(update={"text": f"{s.text}\n\n{text}"}) if s.key == section else s
        for s in kb.sections
    )
    return KnowledgeBase(changed)


def _corrupt(row: dict[str, Any], field: str, mode: str) -> dict[str, Any]:
    value = row.get(field)
    if mode == "missing":
        return {**row, field: None}
    if mode == "blank":
        return {**row, field: "  "}
    return {**row, field: f"  {value.upper()} " if isinstance(value, str) else value}


def apply_incident(
    spec: IncidentSpec,
    tenant: Tenant,
    config: AgentConfig,
    dataset: Dataset,
    llm_settings: dict[str, Any],
) -> IncidentEffect:
    if spec.tenant is not None and spec.tenant != tenant.id:
        raise ConfigError(f"incident {spec.id!r} is for tenant {spec.tenant!r}, not {tenant.id!r}")
    effect = IncidentEffect(
        tenant=tenant, config=config, dataset=dataset, faults=(), llm_settings=dict(llm_settings)
    )
    p = spec.params
    if spec.kind == "api_fault":
        rules = validate_model(p, _FaultParams).rules
        return dataclasses.replace(effect, faults=tuple(rules))
    if spec.kind in ("doc_drift", "retrieval_config_change"):
        patch = validate_model(p, _RetrievalParams).retrieval
        return dataclasses.replace(effect, config=_patch(config, {"retrieval": patch}))
    if spec.kind == "tool_schema_change":
        sp = validate_model(p, _SchemaParams)
        return dataclasses.replace(effect, faults=(FaultRule(op=sp.op, kind="schema_mismatch"),))
    if spec.kind == "model_swap":
        mp = validate_model(p, _ModelSwapParams)
        return dataclasses.replace(
            effect,
            config=_patch(config, {"model": mp.model}),
            llm_settings={**llm_settings, **mp.llm_settings},
        )
    if spec.kind == "prompt_injection":
        ip = validate_model(p, _InjectionParams)
        if ip.target == "kb":
            if ip.section is None:
                raise ConfigError(f"incident {spec.id!r}: a kb injection needs 'section'")
            new_tenant = dataclasses.replace(tenant, kb=_inject_kb(tenant.kb, ip.section, ip.text))
            return dataclasses.replace(effect, tenant=new_tenant)
        cases = []
        for c in dataset.cases:
            if ip.scenarios and c.scenario not in ip.scenarios:
                cases.append(c)
                continue
            ticket = c.ticket.model_copy(update={"body": f"{c.ticket.body}\n\n{ip.text}"})
            cases.append(
                c.model_copy(
                    update={
                        "ticket": ticket,
                        "tags": (*c.tags, "adversarial", "incident:prompt_injection"),
                    }
                )
            )
        return dataclasses.replace(
            effect, dataset=dataset.model_copy(update={"cases": tuple(cases)})
        )
    if spec.kind == "data_quality":
        dp = validate_model(p, _DataQualityParams)
        cases = []
        for c in dataset.cases:
            rows = c.fixtures.get(dp.collection)
            if not rows:
                cases.append(c)
                continue
            rng = _rng(spec, c.id)
            new_rows = []
            for row in rows:
                roll, edge = rng.random(), 0.0
                mode = None
                for m, share in dp.modes.items():
                    edge += share
                    if roll < edge:
                        mode = m
                        break
                new_rows.append(_corrupt(row, dp.field, mode) if mode else row)
            fixtures = {**c.fixtures, dp.collection: new_rows}
            cases.append(
                c.model_copy(
                    update={"fixtures": fixtures, "tags": (*c.tags, "incident:data_quality")}
                )
            )
        return dataclasses.replace(
            effect, dataset=dataset.model_copy(update={"cases": tuple(cases)})
        )
    raise ConfigError(f"incident kind {spec.kind!r} has no implementation")  # pragma: no cover
