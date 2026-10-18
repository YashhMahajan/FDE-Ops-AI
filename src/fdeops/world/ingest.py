"""Ingest of business data: validate, normalize, check references, and report.

Customer data is never as clean as a demo needs. The ingest step loads the records that are
correct, isolates the records that are not, and tells exactly which record, which field and why.
It never removes a record without a report.
"""

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

from pydantic import ValidationError

from fdeops.core.model import FrozenModel
from fdeops.world.state import WorldState

Normalizer = Callable[[dict[str, Any]], dict[str, Any]]


class RecordIssue(FrozenModel):
    collection: str
    index: int
    record_id: str | None
    kind: Literal["invalid", "integrity", "normalized"]
    field: str | None
    message: str


class DataQualityReport(FrozenModel):
    source: str
    total: dict[str, int]
    loaded: dict[str, int]
    quarantined: dict[str, int]
    issues: tuple[RecordIssue, ...]

    @property
    def ok(self) -> bool:
        return not any(self.quarantined.values())

    @property
    def quarantine_rate(self) -> float:
        total = sum(self.total.values())
        return sum(self.quarantined.values()) / total if total else 0.0

    def to_markdown(self, limit: int = 50) -> str:
        lines = [
            f"# Data-quality report: `{self.source}`",
            "",
            "| collection | records | loaded | isolated |",
            "|---|---:|---:|---:|",
        ]
        for name in self.total:
            lines.append(
                f"| `{name}` | {self.total[name]} | {self.loaded[name]} | "
                f"{self.quarantined[name]} |"
            )
        lines += ["", f"Issues: {len(self.issues)}.", ""]
        if self.issues:
            lines += ["| collection | record | type | field | message |", "|---|---|---|---|---|"]
            for i in self.issues[:limit]:
                lines.append(
                    f"| `{i.collection}` | `{i.record_id or i.index}` | {i.kind} | "
                    f"`{i.field or '-'}` | {i.message} |"
                )
        return "\n".join(lines) + "\n"


def _order(names: Sequence[str], references: Mapping[str, Mapping[str, str]]) -> list[str]:
    """Load referenced collections first."""
    done: list[str] = []

    def visit(n: str, stack: tuple[str, ...] = ()) -> None:
        if n in done or n in stack:
            return
        for target in references.get(n, {}).values():
            visit(target, (*stack, n))
        done.append(n)

    for n in names:
        visit(n)
    return [n for n in done if n in names]


def insert_records(
    state: WorldState,
    raw: Mapping[str, Sequence[Mapping[str, Any]]],
    references: Mapping[str, Mapping[str, str]],
    normalizers: Mapping[str, Normalizer],
) -> tuple[list[RecordIssue], Counter[str], Counter[str], Counter[str]]:
    """Validate and insert raw records into ``state``. Returns the issues and the counts."""
    issues: list[RecordIssue] = []
    total: Counter[str] = Counter()
    loaded: Counter[str] = Counter()
    quarantined: Counter[str] = Counter()
    state_cls = type(state)
    for name in _order(state_cls.collection_names(), references):
        if name not in raw:
            continue
        entity_cls = state_cls.entity_type(name)
        collection = state.collection(name)
        for index, original in enumerate(raw[name]):
            total[name] += 1
            row = dict(original)
            rid = str(row.get("id")) if row.get("id") is not None else None
            if name in normalizers:
                normalized = normalizers[name](row)
                changed = sorted(k for k in normalized if normalized.get(k) != row.get(k))
                if changed:
                    issues.append(
                        RecordIssue(
                            collection=name,
                            index=index,
                            record_id=rid,
                            kind="normalized",
                            field=",".join(changed),
                            message="The value was normalized.",
                        )
                    )
                row = normalized
            try:
                entity = entity_cls.model_validate(row)
            except ValidationError as e:
                err = e.errors()[0]
                issues.append(
                    RecordIssue(
                        collection=name,
                        index=index,
                        record_id=rid,
                        kind="invalid",
                        field=".".join(str(p) for p in err["loc"]) or None,
                        message=err["msg"],
                    )
                )
                quarantined[name] += 1
                continue
            if entity.id in collection:
                issues.append(
                    RecordIssue(
                        collection=name,
                        index=index,
                        record_id=entity.id,
                        kind="integrity",
                        field="id",
                        message="duplicate id, the first record stays",
                    )
                )
                quarantined[name] += 1
                continue
            broken = next(
                (
                    (f, t)
                    for f, t in references.get(name, {}).items()
                    if (v := getattr(entity, f, None)) is not None and v not in state.collection(t)
                ),
                None,
            )
            if broken is not None:
                f, t = broken
                issues.append(
                    RecordIssue(
                        collection=name,
                        index=index,
                        record_id=entity.id,
                        kind="integrity",
                        field=f,
                        message=f"refers to an unknown record in {t}",
                    )
                )
                quarantined[name] += 1
                continue
            collection[entity.id] = entity
            loaded[name] += 1
    return issues, total, loaded, quarantined


def ingest(
    raw: Mapping[str, Sequence[Mapping[str, Any]]],
    state_cls: type[WorldState],
    references: Mapping[str, Mapping[str, str]],
    normalizers: Mapping[str, Normalizer],
    source: str,
) -> tuple[WorldState, DataQualityReport]:
    state = state_cls()
    issues, total, loaded, quarantined = insert_records(state, raw, references, normalizers)
    names = state_cls.collection_names()
    report = DataQualityReport(
        source=source,
        total={n: total[n] for n in names},
        loaded={n: loaded[n] for n in names},
        quarantined={n: quarantined[n] for n in names},
        issues=tuple(issues),
    )
    return state, report
