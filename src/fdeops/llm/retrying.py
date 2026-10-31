"""Backoff for rate-limited providers. Free tiers return 429s often; a run should slow down, not
fail. Non-retryable errors (bad request, auth) fail immediately."""

import random

from fdeops.core.clock import Clock, SystemClock
from fdeops.core.errors import InvariantError
from fdeops.llm.openai_compat import LLMUnavailable
from fdeops.llm.types import LLMClient, LLMRequest, LLMResponse


class RetryingLLM:
    def __init__(
        self,
        inner: LLMClient,
        clock: Clock | None = None,
        max_attempts: int = 6,
        base_delay_s: float = 2.0,
        max_delay_s: float = 60.0,
        rng_seed: int | None = None,
    ) -> None:
        self.inner = inner
        self.provider = inner.provider
        self.clock = clock or SystemClock()
        self.max_attempts = max_attempts
        self.base_delay_s = base_delay_s
        self.max_delay_s = max_delay_s
        self._rng = random.Random(rng_seed)  # noqa: S311 - backoff jitter, not a security value

    def complete(self, request: LLMRequest) -> LLMResponse:
        for attempt in range(1, self.max_attempts + 1):
            try:
                return self.inner.complete(request)
            except LLMUnavailable as e:
                if not e.retryable or attempt == self.max_attempts:
                    raise
                ceiling = min(self.base_delay_s * 2 ** (attempt - 1), self.max_delay_s)
                # Jitter: workers that fail together must not retry together.
                self.clock.sleep(ceiling * (0.5 + 0.5 * self._rng.random()))
        raise InvariantError("the retry loop always returns or raises")
