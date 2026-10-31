import json
from typing import Any

import httpx
import pytest

from fdeops.llm.openai_compat import LLMUnavailable, OpenAICompatibleLLM
from fdeops.llm.types import LLMRequest, Message, ToolCall, ToolSpec

REQ = LLMRequest(
    model="qwen",
    messages=(
        Message(role="system", content="sys"),
        Message(role="user", content="hi"),
        Message(
            role="assistant",
            tool_calls=(ToolCall(id="c1", name="f", arguments={"x": 1}, raw_arguments='{"x": 1}'),),
        ),
        Message(role="tool", content='{"ok": true}', tool_call_id="c1", name="f"),
    ),
    tools=(ToolSpec(name="f", description="does f", parameters={"type": "object"}),),
    seed=7,
)


def client(handler: Any) -> OpenAICompatibleLLM:
    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://llm.test/v1")
    return OpenAICompatibleLLM(base_url="http://llm.test/v1", model="qwen", client=http)


def ok_body(message: dict[str, Any], finish: str = "stop") -> dict[str, Any]:
    return {
        "choices": [{"message": message, "finish_reason": finish}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 5},
        "model": "qwen",
    }


def test_request_body_shape() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ok_body({"role": "assistant", "content": "hello"}))

    resp = client(handler).complete(REQ)
    body = seen["body"]
    assert seen["url"] == "http://llm.test/v1/chat/completions"
    assert body["model"] == "qwen" and body["seed"] == 7 and body["temperature"] == 0.0
    assert body["tools"] == [
        {
            "type": "function",
            "function": {"name": "f", "description": "does f", "parameters": {"type": "object"}},
        }
    ]
    assistant = body["messages"][2]
    assert assistant["tool_calls"][0]["function"] == {"name": "f", "arguments": '{"x": 1}'}
    assert body["messages"][3] == {"role": "tool", "content": '{"ok": true}', "tool_call_id": "c1"}
    assert resp.content == "hello"
    assert resp.usage.input_tokens == 11 and resp.usage.output_tokens == 5
    assert resp.provider == "openai_compatible"


def test_maps_tool_calls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=ok_body(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "t1",
                            "type": "function",
                            "function": {"name": "f", "arguments": '{"a": 2}'},
                        }
                    ],
                },
                "tool_calls",
            ),
        )

    resp = client(handler).complete(REQ)
    assert resp.tool_calls == (
        ToolCall(id="t1", name="f", arguments={"a": 2}, raw_arguments='{"a": 2}'),
    )
    assert resp.content == ""
    assert resp.finish_reason == "tool_calls"


def test_invalid_json_arguments_preserved() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=ok_body(
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "t1",
                            "type": "function",
                            "function": {"name": "f", "arguments": "{a: 2"},
                        }
                    ],
                }
            ),
        )

    call = client(handler).complete(REQ).tool_calls[0]
    assert call.arguments is None and call.raw_arguments == "{a: 2"


def test_non_object_arguments_treated_as_invalid() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=ok_body(
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "t1",
                            "type": "function",
                            "function": {"name": "f", "arguments": "[1,2]"},
                        }
                    ],
                }
            ),
        )

    assert client(handler).complete(REQ).tool_calls[0].arguments is None


@pytest.mark.parametrize("status", [429, 500, 503])
def test_5xx_and_429_raise_retryable(status: int) -> None:
    with pytest.raises(LLMUnavailable) as exc:
        client(lambda r: httpx.Response(status, text="busy")).complete(REQ)
    assert exc.value.retryable


def test_4xx_not_retryable() -> None:
    with pytest.raises(LLMUnavailable) as exc:
        client(lambda r: httpx.Response(400, text="bad")).complete(REQ)
    assert not exc.value.retryable


def test_missing_usage_defaults_to_zero() -> None:
    body = {
        "choices": [{"message": {"role": "assistant", "content": "x"}, "finish_reason": "stop"}]
    }
    resp = client(lambda r: httpx.Response(200, json=body)).complete(REQ)
    assert resp.usage.input_tokens == 0


def test_api_key_sent_as_bearer() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json=ok_body({"role": "assistant", "content": "x"}))

    http = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://llm.test/v1")
    OpenAICompatibleLLM(
        base_url="http://llm.test/v1", model="qwen", api_key="sk-test", client=http
    ).complete(REQ)
    assert seen["auth"] == "Bearer sk-test"


@pytest.mark.parametrize(
    "body",
    [
        {"error": {"message": "Provider returned error", "code": 502}},  # HTTP 200 with an error
        {"choices": []},
        {"choices": "none"},
        {"choices": [{"message": {"tool_calls": [{"id": "c", "function": {}}]}}]},
        ["not", "an", "object"],
    ],
)
def test_a_malformed_200_response_is_a_typed_retryable_error(body: Any) -> None:
    llm = client(lambda r: httpx.Response(200, json=body))
    with pytest.raises(LLMUnavailable) as exc:
        llm.complete(REQ)
    assert exc.value.retryable is True


def test_a_200_response_that_is_not_json_is_a_typed_retryable_error() -> None:
    llm = client(lambda r: httpx.Response(200, text="<html>Bad gateway</html>"))
    with pytest.raises(LLMUnavailable, match="not JSON") as exc:
        llm.complete(REQ)
    assert exc.value.retryable is True
