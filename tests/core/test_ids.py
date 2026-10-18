import time

from fdeops.core.ids import new_id, stable_id


def test_stable_id_deterministic_and_prefixed() -> None:
    a = stable_id("case", "ledgerloop", 1, "refund")
    b = stable_id("case", "ledgerloop", 1, "refund")
    c = stable_id("case", "ledgerloop", 2, "refund")
    assert a == b
    assert a != c
    assert a.startswith("case_")
    assert len(a) == len("case_") + 20


def test_new_id_sortable() -> None:
    first = new_id("run")
    time.sleep(0.002)
    second = new_id("run")
    assert first.startswith("run_")
    assert first < second


def test_new_id_unique() -> None:
    assert len({new_id("x") for _ in range(1000)}) == 1000
