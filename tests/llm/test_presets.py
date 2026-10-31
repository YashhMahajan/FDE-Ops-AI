from datetime import UTC, datetime

import httpx
import pytest

from fdeops.core.clock import FakeClock
from fdeops.core.errors import ConfigError
from fdeops.llm.openai_compat import LLMUnavailable
from fdeops.llm.presets import PRESETS, build_provider
from fdeops.llm.retrying import RetryingLLM
from fdeops.llm.types import LLMRequest, LLMResponse, Message

REQ = LLMRequest(model="m", messages=(Message(role="user", content="hi"),))


def test_openrouter_preset_uses_env_key_and_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["title"] = request.headers.get("x-title", "")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    llm = build_provider(
        "openrouter", model="some/free-model:free", transport=httpx.MockTransport(handler)
    )
    assert llm.complete(REQ).content == "ok"
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["auth"] == "Bearer or-test"
    assert seen["title"] == "FDE-Ops-AI"
    assert llm.provider == "openrouter"


def test_openrouter_without_key_is_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ConfigError) as exc:
        build_provider("openrouter", model="x")
    assert "OPENROUTER_API_KEY" in str(exc.value)


def test_local_presets_need_no_key() -> None:
    assert PRESETS["vllm"].api_key_env is None
    assert PRESETS["ollama"].api_key_env is None


def test_unknown_preset() -> None:
    with pytest.raises(ConfigError):
        build_provider("nope", model="x")


class Flaky:
    provider = "flaky"

    def __init__(self, failures: int, retryable: bool = True) -> None:
        self.failures, self.retryable, self.calls = failures, retryable, 0

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        if self.calls <= self.failures:
            raise LLMUnavailable("429", retryable=self.retryable)
        return LLMResponse(content="done", model="m", provider=self.provider)


def test_retrying_llm_backs_off_on_rate_limit() -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    inner = Flaky(failures=2)
    out = RetryingLLM(inner, clock=clock, max_attempts=4, base_delay_s=2.0).complete(REQ)
    assert out.content == "done" and inner.calls == 3
    waited = (clock.now() - datetime(2026, 1, 1, tzinfo=UTC)).total_seconds()
    assert 3.0 <= waited <= 6.0  # two retries: 2 s and 4 s, each cut by up to half (jitter)
    assert RetryingLLM(inner, clock=clock).provider == "flaky"


def test_retrying_llm_gives_up_and_skips_non_retryable() -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    with pytest.raises(LLMUnavailable):
        RetryingLLM(Flaky(failures=10), clock=clock, max_attempts=3).complete(REQ)
    fatal = Flaky(failures=1, retryable=False)
    with pytest.raises(LLMUnavailable):
        RetryingLLM(fatal, clock=clock).complete(REQ)
    assert fatal.calls == 1
