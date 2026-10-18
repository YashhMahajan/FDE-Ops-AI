from fdeops.core.errors import ConfigError
from fdeops.packs.base import DomainPack
from fdeops.packs.billing.pack import BillingPack

_PACKS: dict[str, DomainPack] = {"billing": BillingPack()}


def get_pack(pack_id: str) -> DomainPack:
    try:
        return _PACKS[pack_id]
    except KeyError:
        raise ConfigError(f"unknown pack {pack_id!r}; available: {sorted(_PACKS)}") from None


def available_packs() -> list[str]:
    return sorted(_PACKS)
