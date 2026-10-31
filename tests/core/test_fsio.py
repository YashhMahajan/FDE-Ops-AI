import threading
from pathlib import Path

import pytest

from fdeops.storage.artifacts import LocalArtifactStore


def test_concurrent_writers_to_one_key_do_not_fail_or_mix(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    errors: list[BaseException] = []
    texts = [f"writer-{i}-" + "x" * 200_000 for i in range(8)]

    def write(text: str) -> None:
        try:
            for _ in range(40):
                store.put_text("runs/t/r/run.json", text)
        except BaseException as e:  # noqa: BLE001 - the test collects every failure
            errors.append(e)

    threads = [threading.Thread(target=write, args=(t,)) for t in texts]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert store.get_text("runs/t/r/run.json") in texts  # one whole text, never a mix
    assert [p.name for p in tmp_path.rglob("*.tmp")] == []


def test_a_failed_write_keeps_the_old_file_and_leaves_no_temp_file(tmp_path: Path) -> None:
    from fdeops.core.fsio import atomic_write_text

    target = tmp_path / "state.json"
    atomic_write_text(target, "old")

    class Boom:
        def __str__(self) -> str:
            raise RuntimeError("cannot encode")

    with pytest.raises(TypeError):
        atomic_write_text(target, Boom())  # type: ignore[arg-type]
    assert target.read_text() == "old"
    assert list(tmp_path.glob("*.tmp")) == []
