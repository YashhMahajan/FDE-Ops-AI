from pathlib import Path

import pytest

from fdeops.llm.cassette import CassetteMiss, CassetteStore, request_key
from fdeops.llm.recording import RecordingClient
from fdeops.llm.scripted import ScriptedLLM
from fdeops.llm.types import LLMMode, LLMRequest, LLMResponse, Message, ToolCall, ToolSpec, Usage


def req(text: str = "hello") -> LLMRequest:
    return LLMRequest(
        model="m",
        messages=(Message(role="user", content=text),),
        tools=(
            ToolSpec(
                name="t",
                description="d",
                parameters={"type": "object", "properties": {"b": {}, "a": {}}},
            ),
        ),
    )


class Counting:
    provider = "counting"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            content=f"reply {self.calls}",
            usage=Usage(input_tokens=3, output_tokens=2),
            latency_ms=123.0,
            model=request.model,
            provider=self.provider,
            finish_reason="stop",
        )


def test_record_then_replay_identical(tmp_path: Path) -> None:
    store = CassetteStore(tmp_path / "c.jsonl")
    inner = Counting()
    recorded = RecordingClient(inner, store, LLMMode.RECORD, provider_name="counting").complete(
        req()
    )
    replay = RecordingClient(
        None, CassetteStore(tmp_path / "c.jsonl"), LLMMode.REPLAY, provider_name="counting"
    ).complete(req())
    assert replay == recorded
    assert replay.latency_ms == 123.0
    assert inner.calls == 1


def test_replay_miss_raises_and_never_calls_inner(tmp_path: Path) -> None:
    inner = Counting()
    client = RecordingClient(
        inner, CassetteStore(tmp_path / "c.jsonl"), LLMMode.REPLAY, provider_name="counting"
    )
    with pytest.raises(CassetteMiss):
        client.complete(req())
    assert inner.calls == 0


def test_replay_or_record_records_only_misses(tmp_path: Path) -> None:
    inner = Counting()
    client = RecordingClient(
        inner,
        CassetteStore(tmp_path / "c.jsonl"),
        LLMMode.REPLAY_OR_RECORD,
        provider_name="counting",
    )
    client.complete(req("a"))
    client.complete(req("a"))
    client.complete(req("b"))
    assert inner.calls == 2


def test_live_mode_does_not_record(tmp_path: Path) -> None:
    store = CassetteStore(tmp_path / "c.jsonl")
    RecordingClient(Counting(), store, LLMMode.LIVE, provider_name="counting").complete(req())
    assert len(store) == 0


def test_key_stable_across_schema_dict_order() -> None:
    a = req()
    b = LLMRequest(
        model="m",
        messages=(Message(role="user", content="hello"),),
        tools=(
            ToolSpec(
                name="t",
                description="d",
                parameters={"properties": {"a": {}, "b": {}}, "type": "object"},
            ),
        ),
    )
    assert request_key("p", a) == request_key("p", b)
    assert request_key("p", a) != request_key("q", a)


def test_conflicting_put_raises(tmp_path: Path) -> None:
    store = CassetteStore(tmp_path / "c.jsonl")
    r = req()
    resp = Counting().complete(r)
    store.put("k", r, resp)
    store.put("k", r, resp)  # identical re-put is fine
    with pytest.raises(ValueError):
        store.put("k", r, resp.model_copy(update={"content": "different"}))


def test_store_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "c.jsonl"
    CassetteStore(path).put("k", req(), Counting().complete(req()))
    assert CassetteStore(path).get("k") is not None


def test_replay_requires_store_and_record_requires_inner(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        RecordingClient(None, CassetteStore(tmp_path / "c.jsonl"), LLMMode.RECORD, "x")


def test_scripted_llm_wraps_strings_and_tool_calls() -> None:
    calls = iter(
        ["final text", ToolCall(id="1", name="t", arguments={"a": 1}, raw_arguments='{"a":1}')]
    )
    llm = ScriptedLLM(lambda r: next(calls))
    first = llm.complete(req())
    assert first.content == "final text" and first.tool_calls == ()
    second = llm.complete(req())
    assert second.tool_calls[0].name == "t"
    assert llm.provider == "scripted"
