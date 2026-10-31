from fdeops.llm.openai_compat import LLMUnavailable
from fdeops.llm.retrying import RetryingLLM
from fdeops.llm.types import LLMRequest, LLMResponse, Usage


class SleepRecorder:
    def __init__(self) -> None:
        self.slept: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)

    def now(self):  # type: ignore[no-untyped-def]
        raise NotImplementedError


class Flaky:
    provider = "flaky"

    def __init__(self, failures: int) -> None:
        self.failures = failures

    def complete(self, request: LLMRequest) -> LLMResponse:
        if self.failures > 0:
            self.failures -= 1
            raise LLMUnavailable("HTTP 429", retryable=True)
        return LLMResponse(
            content="ok",
            tool_calls=(),
            usage=Usage(input_tokens=1, output_tokens=1),
            latency_ms=1.0,
            model="m",
            provider="flaky",
            finish_reason="stop",
        )


REQUEST = LLMRequest(model="m", messages=())


def test_backoff_has_jitter_so_that_many_workers_do_not_retry_together() -> None:
    delays: list[list[float]] = []
    for seed in range(2):
        clock = SleepRecorder()
        llm = RetryingLLM(Flaky(3), clock=clock, base_delay_s=2.0, rng_seed=seed)  # type: ignore[arg-type]
        assert llm.complete(REQUEST).content == "ok"
        delays.append(clock.slept)
    assert delays[0] != delays[1]
    for slept in delays:
        for attempt, d in enumerate(slept):
            ceiling = min(2.0 * 2**attempt, 60.0)
            assert 0.5 * ceiling <= d <= ceiling  # between half and the full exponential delay
