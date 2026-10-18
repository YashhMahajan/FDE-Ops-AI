"""Versioned knowledge base.

Documents are markdown files named ``<doc_id>.v<N>.md`` with YAML frontmatter
(``doc_id``, ``title``, ``version``, ``effective_from``). Sections are level-2 headings with an
explicit anchor: ``## Refund window {#refund-window}``. A section's identity across versions is its
``key`` (``doc_id#anchor``); each version is effective from its ``effective_from`` until the next
version's. That makes "what did the docs say on date D" answerable, and stale knowledge detectable
exactly rather than by guesswork.
"""

import itertools
import re
from collections import defaultdict
from datetime import date
from functools import cached_property
from pathlib import Path

import yaml
from pydantic import ValidationError

from fdeops.core.config import format_validation_error
from fdeops.core.errors import ConfigError
from fdeops.core.hashing import content_hash
from fdeops.core.model import FrozenModel

_FILENAME = re.compile(r"^(?P<doc_id>[a-z0-9][a-z0-9-]*)\.v(?P<version>\d+)\.md$")
_HEADING = re.compile(r"^##\s+(?P<title>.+?)\s*(?:\{#(?P<anchor>[a-z0-9][a-z0-9-]*)\})?\s*$")


class Section(FrozenModel):
    key: str
    doc_id: str
    anchor: str
    title: str
    text: str
    version: int
    effective_from: date
    effective_to: date | None = None

    @property
    def uid(self) -> str:
        return f"{self.key}@v{self.version}"


class _Frontmatter(FrozenModel):
    doc_id: str
    title: str
    version: int
    effective_from: date


class KnowledgeBase:
    def __init__(self, sections: tuple[Section, ...]) -> None:
        self.sections = tuple(sorted(sections, key=lambda s: (s.key, s.version)))
        self._by_key: dict[str, list[Section]] = defaultdict(list)
        for s in self.sections:
            self._by_key[s.key].append(s)

    def __contains__(self, key: object) -> bool:
        return key in self._by_key

    def keys(self) -> list[str]:
        return sorted(self._by_key)

    def get(self, key: str, version: int | None = None) -> Section:
        versions = self._by_key.get(key)
        if not versions:
            raise KeyError(f"unknown section {key!r}")
        if version is None:
            return versions[-1]
        for s in versions:
            if s.version == version:
                return s
        raise KeyError(f"section {key!r} has no version {version}")

    def effective(self, key: str, on: date) -> Section | None:
        for s in self._by_key.get(key, []):
            if s.effective_from <= on and not self.is_stale(s, on):
                return s
        return None

    def as_of(self, on: date) -> list[Section]:
        return [s for k in self.keys() if (s := self.effective(k, on)) is not None]

    def is_stale(self, section: Section, on: date) -> bool:
        return section.effective_to is not None and section.effective_to <= on

    @cached_property
    def content_hash(self) -> str:
        return content_hash(self.sections)


def _parse_file(path: Path) -> tuple[_Frontmatter, list[tuple[str, str, str]]]:
    m = _FILENAME.match(path.name)
    if not m:
        raise ConfigError("KB filename must look like <doc_id>.v<N>.md", path)
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ConfigError("missing YAML frontmatter (file must start with '---')", path)
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ConfigError("unterminated YAML frontmatter", path)
    try:
        front = _Frontmatter.model_validate(yaml.safe_load(text[4:end]) or {})
    except (yaml.YAMLError, ValidationError) as e:
        detail = format_validation_error(e) if isinstance(e, ValidationError) else str(e)
        raise ConfigError(f"invalid frontmatter: {detail}", path) from e
    if front.doc_id != m["doc_id"] or front.version != int(m["version"]):
        raise ConfigError("frontmatter doc_id/version do not match the filename", path)

    sections: list[tuple[str, str, str]] = []
    current: tuple[str, str] | None = None
    buf: list[str] = []
    seen: set[str] = set()
    for line in text[end + 5 :].splitlines():
        h = _HEADING.match(line)
        if h:
            if current:
                sections.append((current[0], current[1], "\n".join(buf).strip()))
            if not h["anchor"]:
                raise ConfigError(f"section {h['title']!r} has no {{#anchor}}", path)
            if h["anchor"] in seen:
                raise ConfigError(f"duplicate anchor {h['anchor']!r}", path)
            seen.add(h["anchor"])
            current, buf = (h["anchor"], h["title"]), []
        elif current:
            buf.append(line)
    if current:
        sections.append((current[0], current[1], "\n".join(buf).strip()))
    if not sections:
        raise ConfigError("document has no sections", path)
    return front, sections


def load_kb(directory: Path) -> KnowledgeBase:
    if not directory.is_dir():
        raise ConfigError("knowledge base directory not found", directory)
    docs: dict[str, list[tuple[_Frontmatter, list[tuple[str, str, str]], Path]]] = defaultdict(list)
    for path in sorted(directory.glob("*.md")):
        front, sections = _parse_file(path)
        docs[front.doc_id].append((front, sections, path))

    out: list[Section] = []
    for doc_id, versions in docs.items():
        versions.sort(key=lambda v: v[0].version)
        for (prev, _, _), (cur, _, path) in itertools.pairwise(versions):
            if cur.effective_from <= prev.effective_from:
                raise ConfigError(
                    f"version {cur.version} of {doc_id!r} must take effect after version "
                    f"{prev.version}",
                    path,
                )
        for i, (front, sections, _) in enumerate(versions):
            nxt = versions[i + 1][0].effective_from if i + 1 < len(versions) else None
            for anchor, title, body in sections:
                out.append(
                    Section(
                        key=f"{doc_id}#{anchor}",
                        doc_id=doc_id,
                        anchor=anchor,
                        title=title,
                        text=body,
                        version=front.version,
                        effective_from=front.effective_from,
                        effective_to=nxt,
                    )
                )
    return KnowledgeBase(tuple(out))
