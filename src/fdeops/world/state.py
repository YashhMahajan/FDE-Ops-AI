"""World state as typed entity collections, plus structural diffing.

A ``WorldState`` subclass declares each collection as ``dict[str, <Entity subclass>]``. Entities are
immutable; updates replace the entity. Diffing before/after an episode yields the exact set of
state changes the agent caused, which is how task outcomes are graded.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Literal, Self, get_args, get_origin

from pydantic import BaseModel, ConfigDict

from fdeops.core.model import FrozenModel


class Entity(FrozenModel):
    id: str


class StateChange(FrozenModel):
    collection: str
    entity_id: str
    kind: Literal["created", "updated", "deleted"]
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    changed_fields: tuple[str, ...]


class WorldState(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    @classmethod
    def collection_names(cls) -> tuple[str, ...]:
        return tuple(cls.model_fields)

    @classmethod
    def entity_type(cls, name: str) -> type[Entity]:
        if name not in cls.model_fields:
            raise KeyError(f"unknown collection {name!r} on {cls.__name__}")
        annotation = cls.model_fields[name].annotation
        if get_origin(annotation) is not dict:
            raise TypeError(f"collection {name!r} must be annotated as dict[str, Entity]")
        entity = get_args(annotation)[1]
        if not (isinstance(entity, type) and issubclass(entity, Entity)):
            raise TypeError(f"collection {name!r} values must be Entity subclasses")
        return entity

    def copy(self) -> Self:  # type: ignore[override]
        # Entities are frozen, so copying the dicts is a full logical deep copy.
        return self.model_copy(update={n: dict(getattr(self, n)) for n in self.collection_names()})

    def collection(self, name: str) -> dict[str, Entity]:
        self.entity_type(name)
        value: dict[str, Entity] = getattr(self, name)
        return value

    def upsert(self, name: str, entity: Entity) -> None:
        expected = self.entity_type(name)
        if not isinstance(entity, expected):
            raise TypeError(f"{name!r} holds {expected.__name__}, got {type(entity).__name__}")
        self.collection(name)[entity.id] = entity

    def insert_fixtures(self, fixtures: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
        for name, rows in fixtures.items():
            entity_cls = self.entity_type(name)
            for row in rows:
                self.upsert(name, entity_cls.model_validate(dict(row)))


def diff_states(before: WorldState, after: WorldState) -> list[StateChange]:
    if type(before) is not type(after):
        raise TypeError("cannot diff states of different types")
    changes: list[StateChange] = []
    for name in before.collection_names():
        old, new = before.collection(name), after.collection(name)
        for entity_id in sorted(set(old) | set(new)):
            a = old.get(entity_id)
            b = new.get(entity_id)
            if a == b:
                continue
            a_dump = a.model_dump(mode="json") if a is not None else None
            b_dump = b.model_dump(mode="json") if b is not None else None
            if a_dump is None:
                kind: Literal["created", "updated", "deleted"] = "created"
                fields = tuple(sorted(b_dump or {}))
            elif b_dump is None:
                kind, fields = "deleted", tuple(sorted(a_dump))
            else:
                kind = "updated"
                keys = set(a_dump) | set(b_dump)
                fields = tuple(sorted(k for k in keys if a_dump.get(k) != b_dump.get(k)))
            changes.append(
                StateChange(
                    collection=name,
                    entity_id=entity_id,
                    kind=kind,
                    before=a_dump,
                    after=b_dump,
                    changed_fields=fields,
                )
            )
    changes.sort(key=lambda c: (c.collection, c.entity_id))
    return changes


def get_path(data: Mapping[str, Any] | None, dotted: str) -> Any:
    """Read ``a.b.c`` from nested mappings; missing segments yield ``None``."""
    current: Any = data
    for part in dotted.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current
