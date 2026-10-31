"""Artifact store for large items (run records, traces, reports). The local store is a folder.

A deployment can add an S3-compatible store with the same three functions.
"""

from pathlib import Path
from typing import Protocol

from fdeops.core.errors import ConfigError
from fdeops.core.fsio import atomic_write_text


class ArtifactStore(Protocol):
    def put_text(self, key: str, text: str) -> str: ...

    def get_text(self, uri: str) -> str: ...

    def exists(self, uri: str) -> bool: ...


class LocalArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents and p != self.root:
            raise ConfigError(f"artifact key {key!r} is outside the artifact store")
        return p

    def put_text(self, key: str, text: str) -> str:
        atomic_write_text(self._path(key), text)
        return key

    def get_text(self, uri: str) -> str:
        p = self._path(uri)
        if not p.exists():
            raise ConfigError(f"artifact {uri!r} not found")
        return p.read_text(encoding="utf-8")

    def exists(self, uri: str) -> bool:
        return self._path(uri).exists()

    def list(self, prefix: str) -> list[str]:
        base = self._path(prefix)
        if not base.exists():
            return []
        return sorted(str(p.relative_to(self.root)) for p in base.rglob("*") if p.is_file())
