"""Versioned, content-hashed datasets with a stable dev/test split.

Split membership depends only on the case id, so it never shifts when seeds or counts change;
``dev`` is for diagnosis and tuning, ``test`` is held out for release gates.
"""

import hashlib
import json
import random
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from fdeops.core.errors import ConfigError
from fdeops.core.fsio import atomic_write_text
from fdeops.core.hashing import canonical_json, content_hash
from fdeops.core.ids import stable_id
from fdeops.core.model import FrozenModel
from fdeops.retrieval.kb import KnowledgeBase
from fdeops.world.cases import Case, CaseProvenance, Split
from fdeops.world.scenario import Scenario, ScenarioContext
from fdeops.world.state import WorldState

GENERATOR = "fdeops.world.dataset"


class DatasetSpec(FrozenModel):
    name: str
    version: int
    seed: int
    cases_per_scenario: dict[str, int]
    test_fraction: float = 0.6
    now: datetime


class Dataset(FrozenModel):
    tenant_id: str
    name: str
    version: int
    split: Split
    cases: tuple[Case, ...]
    world_hash: str
    kb_hash: str
    generator_version: str

    @property
    def content_hash(self) -> str:
        # Not cached: pydantic's model_copy would copy a cached value into a changed copy.
        return content_hash(self)

    @property
    def ref(self) -> str:
        return f"{self.tenant_id}/{self.name}@v{self.version}/{self.split}"


def assign_split(case_id: str, test_fraction: float) -> Split:
    bucket = int(hashlib.sha256(case_id.encode()).hexdigest(), 16) % 1000
    return "test" if bucket < round(test_fraction * 1000) else "dev"


def _seed_for(*parts: object) -> int:
    return int(hashlib.sha256(canonical_json(list(parts)).encode()).hexdigest()[:16], 16)


def build_datasets(
    tenant_id: str,
    spec: DatasetSpec,
    scenarios: Mapping[str, Scenario],
    base_world: WorldState,
    policy: Any,
    kb: KnowledgeBase,
    generator_version: str,
) -> dict[str, Dataset]:
    unknown = set(spec.cases_per_scenario) - set(scenarios)
    if unknown:
        raise ConfigError(f"dataset {spec.name!r} references unknown scenarios: {sorted(unknown)}")
    by_split: dict[str, list[Case]] = {"dev": [], "test": []}
    for scenario_id in sorted(spec.cases_per_scenario):
        scenario = scenarios[scenario_id]
        for variant in range(spec.cases_per_scenario[scenario_id]):
            ctx = ScenarioContext(
                rng=random.Random(_seed_for(spec.seed, scenario_id, variant)),
                base_world=base_world,
                policy=policy,
                kb=kb,
                now=spec.now,
                tenant_id=tenant_id,
                variant=variant,
            )
            draft = scenario.generate(ctx)
            case_id = stable_id("case", tenant_id, spec.name, spec.version, scenario_id, variant)
            split = assign_split(case_id, spec.test_fraction)
            case = Case(
                **draft.model_dump(),
                id=case_id,
                split=split,
                provenance=CaseProvenance(
                    generator=GENERATOR,
                    generator_version=generator_version,
                    scenario=scenario_id,
                    seed=spec.seed,
                    variant=variant,
                ),
            )
            by_split[split].append(case)
    world_hash = content_hash(base_world)
    return {
        split: Dataset(
            tenant_id=tenant_id,
            name=spec.name,
            version=spec.version,
            split=split,
            cases=tuple(cases),
            world_hash=world_hash,
            kb_hash=kb.content_hash,
            generator_version=generator_version,
        )
        for split, cases in by_split.items()
    }


def dataset_dir(root: Path, tenant_id: str, name: str, version: int) -> Path:
    return root / tenant_id / f"{name}@v{version}"


def save_dataset(ds: Dataset, root: Path) -> Path:
    out = dataset_dir(root, ds.tenant_id, ds.name, ds.version)
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        out / f"{ds.split}.jsonl", "".join(canonical_json(case) + "\n" for case in ds.cases)
    )
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest.update(
        {
            "tenant_id": ds.tenant_id,
            "name": ds.name,
            "version": ds.version,
            "world_hash": ds.world_hash,
            "kb_hash": ds.kb_hash,
            "generator_version": ds.generator_version,
        }
    )
    manifest.setdefault("splits", {})[ds.split] = {
        "content_hash": ds.content_hash,
        "n_cases": len(ds.cases),
        "scenarios": _counts(c.scenario for c in ds.cases),
    }
    atomic_write_text(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return out


def _counts(items: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        out[item] = out.get(item, 0) + 1
    return dict(sorted(out.items()))


def load_dataset(path: Path, split: Split) -> Dataset:
    manifest_path = path / "manifest.json"
    if not manifest_path.exists():
        raise ConfigError("dataset manifest.json not found", path)
    manifest = json.loads(manifest_path.read_text())
    if split not in manifest.get("splits", {}):
        raise ConfigError(f"dataset has no split {split!r}", path)
    cases_file = path / f"{split}.jsonl"
    cases = tuple(
        Case.model_validate_json(line)
        for line in cases_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    ds = Dataset(
        tenant_id=manifest["tenant_id"],
        name=manifest["name"],
        version=manifest["version"],
        split=split,
        cases=cases,
        world_hash=manifest["world_hash"],
        kb_hash=manifest["kb_hash"],
        generator_version=manifest["generator_version"],
    )
    expected = manifest["splits"][split]["content_hash"]
    if ds.content_hash != expected:
        raise ConfigError(
            f"content hash mismatch for split {split!r}: manifest {expected}, file "
            f"{ds.content_hash} (dataset was modified after it was built)",
            cases_file,
        )
    return ds
