import pytest
from fdeops.world.state import Entity, WorldState, diff_states, get_path
from pydantic import ValidationError


class Widget(Entity):
    color: str
    size: int = 1


class Note(Entity):
    text: str


class ToyState(WorldState):
    widgets: dict[str, Widget] = {}
    notes: dict[str, Note] = {}


def make() -> ToyState:
    s = ToyState()
    s.upsert("widgets", Widget(id="w1", color="red"))
    s.upsert("widgets", Widget(id="w2", color="blue"))
    return s


def test_diff_empty_when_equal() -> None:
    a = make()
    assert diff_states(a, a.copy()) == []


def test_diff_created_updated_deleted() -> None:
    before = make()
    after = before.copy()
    after.upsert("widgets", Widget(id="w1", color="green"))
    del after.widgets["w2"]
    after.upsert("notes", Note(id="n1", text="hi"))
    changes = diff_states(before, after)
    kinds = {(c.collection, c.entity_id): c for c in changes}
    assert kinds[("widgets", "w1")].kind == "updated"
    assert kinds[("widgets", "w1")].changed_fields == ("color",)
    assert kinds[("widgets", "w1")].before == {"id": "w1", "color": "red", "size": 1}
    assert kinds[("widgets", "w2")].kind == "deleted"
    assert kinds[("notes", "n1")].kind == "created"
    assert kinds[("notes", "n1")].after == {"id": "n1", "text": "hi"}
    assert [(c.collection, c.entity_id) for c in changes] == sorted(kinds)


def test_copy_is_deep() -> None:
    a = make()
    b = a.copy()
    b.upsert("widgets", Widget(id="w3", color="x"))
    assert "w3" not in a.widgets


def test_upsert_rejects_wrong_type() -> None:
    s = ToyState()
    with pytest.raises(TypeError):
        s.upsert("widgets", Note(id="n", text="t"))


def test_insert_fixtures_validates_types() -> None:
    s = ToyState()
    s.insert_fixtures({"widgets": [{"id": "w9", "color": "c", "size": 4}]})
    assert s.widgets["w9"].size == 4
    with pytest.raises(ValidationError):
        s.insert_fixtures({"widgets": [{"id": "w10", "color": "c", "size": "big"}]})


def test_insert_fixtures_unknown_collection() -> None:
    with pytest.raises(KeyError):
        ToyState().insert_fixtures({"gadgets": [{"id": "g"}]})


def test_get_path() -> None:
    d = {"a": {"b": {"c": 3}}, "x": None}
    assert get_path(d, "a.b.c") == 3
    assert get_path(d, "a.z") is None
    assert get_path(d, "x.y") is None
