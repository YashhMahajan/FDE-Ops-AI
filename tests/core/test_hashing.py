from datetime import UTC, date, datetime
from enum import StrEnum

from hypothesis import given
from hypothesis import strategies as st

from fdeops.core.hashing import canonical_json, content_hash
from fdeops.core.model import FrozenModel


class Color(StrEnum):
    RED = "red"


class Thing(FrozenModel):
    name: str
    when: date


def test_canonical_json_key_order_independent() -> None:
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_canonical_json_handles_models_dates_enums_sets() -> None:
    value = {
        "m": Thing(name="x", when=date(2026, 1, 2)),
        "t": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        "e": Color.RED,
        "s": {3, 1, 2},
        "tup": (1, 2),
    }
    out = canonical_json(value)
    assert '"e":"red"' in out
    assert '"s":[1,2,3]' in out
    assert '"m":{"name":"x","when":"2026-01-02"}' in out
    assert '"t":"2026-01-02T03:04:05+00:00"' in out
    assert '"tup":[1,2]' in out


def test_content_hash_prefix() -> None:
    h = content_hash({"a": 1})
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64


@given(st.dictionaries(st.text(max_size=5), st.integers(), max_size=8))
def test_canonical_json_insertion_order_invariant(d: dict[str, int]) -> None:
    reversed_d = dict(reversed(list(d.items())))
    assert canonical_json(d) == canonical_json(reversed_d)
