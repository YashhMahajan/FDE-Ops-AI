from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fdeops.core.config import load_model, load_yaml, validate_model
from fdeops.core.errors import ConfigError
from fdeops.packs.base import DomainPack
from fdeops.packs.registry import get_pack
from fdeops.retrieval.kb import KnowledgeBase, load_kb
from fdeops.tenancy.config import TenantConfig
from fdeops.world.dataset import Dataset, DatasetSpec, build_datasets
from fdeops.world.ingest import DataQualityReport, ingest
from fdeops.world.state import WorldState


@dataclass(frozen=True)
class Tenant:
    config: TenantConfig
    root: Path
    pack: DomainPack
    policy: Any
    kb: KnowledgeBase
    base_world: WorldState
    world_now: datetime
    data_quality: DataQualityReport

    @property
    def id(self) -> str:
        return self.config.id

    @property
    def scopes(self) -> frozenset[str]:
        return frozenset(self.config.agent_scopes)

    @property
    def company(self) -> str:
        return self.config.display_name.removesuffix(" (fictional)")

    def dataset_spec(self, name: str) -> DatasetSpec:
        for spec in self.config.datasets:
            if spec.name == name:
                return spec
        raise ConfigError(f"tenant {self.id!r} has no dataset {name!r}")

    def build_datasets(self, name: str) -> dict[str, Dataset]:
        return build_datasets(
            self.id,
            self.dataset_spec(name),
            self.pack.scenarios(),
            self.base_world,
            self.policy,
            self.kb,
            self.pack.generator_version,
        )


def load_tenant(root: Path) -> Tenant:
    cfg_path = root / "tenant.yaml"
    raw = load_yaml(cfg_path)
    if raw.get("fictional") is not True:
        raise ConfigError(
            "tenants in this repository must be fictional (set fictional: true)", cfg_path
        )
    config = validate_model(raw, TenantConfig, cfg_path)
    pack = get_pack(config.pack)
    extra = set(config.agent_scopes) - set(pack.agent_scopes)
    if extra:
        raise ConfigError(
            f"agent_scopes not offered by pack {pack.id!r}: {sorted(extra)}", cfg_path
        )
    policy = load_model(root / config.policy_file, pack.policy_model)
    kb = load_kb(root / config.kb_dir)
    world_spec = validate_model(config.world.spec, pack.world_spec_model, cfg_path)
    generated = pack.generate_world(world_spec, config.world.now)
    raw = {
        n: [e.model_dump(mode="json") for e in generated.collection(n).values()]
        for n in generated.collection_names()
    }
    base_world, quality = ingest(
        raw,
        type(generated),
        pack.references,
        pack.normalizers,
        source=f"{config.id}/generated-world",
    )
    for spec in config.datasets:
        unknown = set(spec.cases_per_scenario) - set(pack.scenarios())
        if unknown:
            raise ConfigError(
                f"dataset {spec.name!r} uses unknown scenarios {sorted(unknown)}", cfg_path
            )
    return Tenant(
        config=config,
        root=root,
        pack=pack,
        policy=policy,
        kb=kb,
        base_world=base_world,
        world_now=config.world.now,
        data_quality=quality,
    )
