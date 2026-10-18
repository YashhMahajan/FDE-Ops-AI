from fdeops.world.ingest import ingest
from fdeops.world.state import Entity, WorldState


class Account(Entity):
    name: str


class Member(Entity):
    account_id: str
    email: str


class Toy(WorldState):
    accounts: dict[str, Account] = {}
    members: dict[str, Member] = {}


REFS = {"members": {"account_id": "accounts"}}


def norm_member(row: dict) -> dict:  # type: ignore[type-arg]
    return {**row, "email": str(row.get("email", "")).strip().lower()}


def test_clean_data_loads_without_issues() -> None:
    raw = {
        "accounts": [{"id": "a1", "name": "A"}],
        "members": [{"id": "m1", "account_id": "a1", "email": "x@a.example"}],
    }
    state, report = ingest(raw, Toy, REFS, {"members": norm_member}, source="test")
    assert report.ok and report.issues == ()
    assert report.loaded == {"accounts": 1, "members": 1}
    assert state.members["m1"].email == "x@a.example"


def test_invalid_record_is_quarantined_with_reason() -> None:
    raw = {"accounts": [{"id": "a1", "name": "A"}, {"id": "a2"}]}
    state, report = ingest(raw, Toy, REFS, {}, source="test")
    assert "a2" not in state.accounts
    assert report.quarantined == {"accounts": 1, "members": 0}
    issue = report.issues[0]
    assert issue.kind == "invalid" and issue.field == "name" and issue.record_id == "a2"
    assert not report.ok


def test_orphan_record_is_integrity_error() -> None:
    raw = {
        "accounts": [{"id": "a1", "name": "A"}],
        "members": [{"id": "m1", "account_id": "missing", "email": "x@a.example"}],
    }
    state, report = ingest(raw, Toy, REFS, {}, source="test")
    assert state.members == {}
    assert report.issues[0].kind == "integrity" and report.issues[0].field == "account_id"


def test_duplicate_ids_keep_first_and_report() -> None:
    raw = {"accounts": [{"id": "a1", "name": "A"}, {"id": "a1", "name": "B"}]}
    state, report = ingest(raw, Toy, REFS, {}, source="test")
    assert state.accounts["a1"].name == "A"
    assert report.issues[0].kind == "integrity" and "duplicate" in report.issues[0].message


def test_normalization_is_reported_not_silent() -> None:
    raw = {
        "accounts": [{"id": "a1", "name": "A"}],
        "members": [{"id": "m1", "account_id": "a1", "email": "  X@A.example "}],
    }
    state, report = ingest(raw, Toy, REFS, {"members": norm_member}, source="test")
    assert state.members["m1"].email == "x@a.example"
    assert [i.kind for i in report.issues] == ["normalized"]
    assert report.ok  # a normalization is not a data loss


def test_markdown_report() -> None:
    raw = {"accounts": [{"id": "a2"}]}
    _, report = ingest(raw, Toy, REFS, {}, source="export-2026-09-15")
    md = report.to_markdown()
    assert "export-2026-09-15" in md and "a2" in md
