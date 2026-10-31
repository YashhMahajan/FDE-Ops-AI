"""API keys. The database keeps only a SHA-256 hash of each key."""

import hashlib
import secrets
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from fdeops.core.errors import ConfigError
from fdeops.core.ids import new_id
from fdeops.storage.db import ApiKeyRow, utcnow
from fdeops.storage.roles import Role

__all__ = ["KeyStore", "Principal", "Role"]


@dataclass(frozen=True)
class Principal:
    key_id: str
    name: str
    role: Role
    tenant_id: str | None
    """``None`` only for an admin key that can see all tenants."""

    def can_access(self, tenant_id: str) -> bool:
        return (self.role == Role.ADMIN and self.tenant_id is None) or self.tenant_id == tenant_id


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class KeyStore:
    def __init__(self, session: Session) -> None:
        self.s = session

    def create(self, tenant_id: str | None, name: str, role: Role) -> tuple[str, ApiKeyRow]:
        if tenant_id is None and role != Role.ADMIN:
            raise ConfigError("only an admin key can be without a tenant")
        secret = "fdo_" + secrets.token_urlsafe(24)
        row = ApiKeyRow(
            key_id=new_id("key"),
            tenant_id=tenant_id,
            name=name,
            role=role.value,
            key_hash=_hash(secret),
            prefix=secret[:8],
            created_at=utcnow(),
        )
        self.s.add(row)
        self.s.flush()
        return secret, row

    def authenticate(self, secret: str) -> Principal | None:
        row = self.s.scalar(select(ApiKeyRow).where(ApiKeyRow.key_hash == _hash(secret)))
        if row is None or row.revoked_at is not None:
            return None
        return Principal(
            key_id=row.key_id, name=row.name, role=Role(row.role), tenant_id=row.tenant_id
        )

    def revoke(self, key_id: str) -> None:
        row = self.s.get(ApiKeyRow, key_id)
        if row is None:
            raise ConfigError(f"no key {key_id}")
        row.revoked_at = utcnow()

    def list(self, tenant_id: str | None = None) -> list[ApiKeyRow]:
        q = select(ApiKeyRow)
        if tenant_id is not None:
            q = q.where(ApiKeyRow.tenant_id == tenant_id)
        return list(self.s.scalars(q))
