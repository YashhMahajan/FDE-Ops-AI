from fdeops.core.errors import InvariantError
from fdeops.llm.cassette import CassetteMiss, CassetteStore, request_key
from fdeops.llm.types import LLMClient, LLMMode, LLMRequest, LLMResponse


class RecordingClient:
    """Wraps a provider with cassette record/replay according to ``mode``."""

    def __init__(
        self, inner: LLMClient | None, store: CassetteStore, mode: LLMMode, provider_name: str
    ) -> None:
        if mode != LLMMode.REPLAY and inner is None:
            raise ValueError(f"mode {mode} needs a live provider")
        self.inner = inner
        self.store = store
        self.mode = mode
        self.provider = provider_name

    def complete(self, request: LLMRequest) -> LLMResponse:
        key = request_key(self.provider, request)
        if self.mode in (LLMMode.REPLAY, LLMMode.REPLAY_OR_RECORD):
            hit = self.store.get(key)
            if hit is not None:
                return hit
            if self.mode == LLMMode.REPLAY:
                raise CassetteMiss(f"no recorded response for {key} in {self.store.path}")
        if self.inner is None:
            raise InvariantError("self.inner must be set here")
        response = self.inner.complete(request)
        if self.mode != LLMMode.LIVE:
            self.store.put(key, request, response)
        return response
