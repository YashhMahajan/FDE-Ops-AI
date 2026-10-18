from datetime import date
from pathlib import Path

import pytest

from fdeops.core.errors import ConfigError
from fdeops.retrieval.kb import load_kb

GOOD = Path(__file__).parent.parent / "fixtures" / "kb" / "good"


def test_loads_sections_with_keys() -> None:
    kb = load_kb(GOOD)
    keys = {s.key for s in kb.sections}
    assert keys == {"refund-policy#refund-window", "refund-policy#payout", "plans#available"}
    s = kb.get("refund-policy#refund-window", version=1)
    assert s.title == "Refund window"
    assert "30 days" in s.text
    assert s.uid == "refund-policy#refund-window@v1"


def test_as_of_picks_effective_version() -> None:
    kb = load_kb(GOOD)
    before = {s.key: s.version for s in kb.as_of(date(2026, 8, 31))}
    after = {s.key: s.version for s in kb.as_of(date(2026, 9, 1))}
    assert before["refund-policy#refund-window"] == 1
    assert after["refund-policy#refund-window"] == 2
    assert kb.as_of(date(2025, 12, 31)) == []


def test_effective_to_set_from_next_version() -> None:
    kb = load_kb(GOOD)
    assert kb.get("refund-policy#refund-window", 1).effective_to == date(2026, 9, 1)
    assert kb.get("refund-policy#refund-window", 2).effective_to is None
    assert kb.get("refund-policy#refund-window").version == 2


def test_is_stale() -> None:
    kb = load_kb(GOOD)
    v1 = kb.get("refund-policy#refund-window", 1)
    assert not kb.is_stale(v1, date(2026, 8, 31))
    assert kb.is_stale(v1, date(2026, 9, 1))


def test_content_hash_stable() -> None:
    assert load_kb(GOOD).content_hash == load_kb(GOOD).content_hash


def _write(tmp: Path, name: str, body: str) -> None:
    (tmp / name).write_text(body)


def test_duplicate_anchor_error_names_file(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "a.v1.md",
        "---\ndoc_id: a\ntitle: A\nversion: 1\neffective_from: 2026-01-01\n---\n"
        "## One {#x}\nt\n## Two {#x}\nt\n",
    )
    with pytest.raises(ConfigError) as exc:
        load_kb(tmp_path)
    assert "a.v1.md" in str(exc.value)
    assert "duplicate anchor" in str(exc.value)


def test_missing_frontmatter_error(tmp_path: Path) -> None:
    _write(tmp_path, "a.v1.md", "## One {#x}\ntext\n")
    with pytest.raises(ConfigError) as exc:
        load_kb(tmp_path)
    assert "frontmatter" in str(exc.value)


def test_doc_id_must_match_filename(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "a.v1.md",
        "---\ndoc_id: b\ntitle: A\nversion: 1\neffective_from: 2026-01-01\n---\n## One {#x}\nt\n",
    )
    with pytest.raises(ConfigError):
        load_kb(tmp_path)


def test_section_without_anchor_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "a.v1.md",
        "---\ndoc_id: a\ntitle: A\nversion: 1\neffective_from: 2026-01-01\n---\n## One\nt\n",
    )
    with pytest.raises(ConfigError) as exc:
        load_kb(tmp_path)
    assert "anchor" in str(exc.value)


def test_versions_must_increase_in_time(tmp_path: Path) -> None:
    head = "---\ndoc_id: a\ntitle: A\nversion: {v}\neffective_from: {d}\n---\n## One {{#x}}\nt\n"
    _write(tmp_path, "a.v1.md", head.format(v=1, d="2026-05-01"))
    _write(tmp_path, "a.v2.md", head.format(v=2, d="2026-04-01"))
    with pytest.raises(ConfigError):
        load_kb(tmp_path)


def test_section_removed_in_later_version_is_not_current(tmp_path: Path) -> None:
    head = "---\ndoc_id: a\ntitle: A\nversion: {v}\neffective_from: {d}\n---\n"
    _write(
        tmp_path,
        "a.v1.md",
        head.format(v=1, d="2026-01-01") + "## Keep {#keep}\nk\n## Old {#old}\no\n",
    )
    _write(tmp_path, "a.v2.md", head.format(v=2, d="2026-06-01") + "## Keep {#keep}\nk2\n")
    kb = load_kb(tmp_path)
    assert {s.key for s in kb.as_of(date(2026, 7, 1))} == {"a#keep"}
    assert {s.key for s in kb.as_of(date(2026, 2, 1))} == {"a#keep", "a#old"}
