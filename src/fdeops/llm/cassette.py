"""Content-addressed cassettes of model calls.

A response is stored under the hash of (provider, canonical request). Replaying a cassette gives
bit-identical model outputs, with the originally measured latency and token usage, so evaluations
are reproducible and free, and CI can regression-test an agent without a GPU or an API key.
"""

import json
import threading
from pathlib import Path

from fdeops.core.errors import FdeOpsError
from fdeops.core.hashing import canonical_json, content_hash
from fdeops.llm.types import LLMRequest, LLMResponse


class CassetteMiss(FdeOpsError):
    """Replay mode asked for a response that was never recorded."""


def request_key(provider: str, request: LLMRequest) -> str:
    return content_hash({"provider": provider, "request": request})


class CassetteStore:
    """Append-only JSONL store. Safe for concurrent use within one process."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._index: dict[str, LLMResponse] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self._index[row["key"]] = LLMResponse.model_validate(row["response"])

    def __len__(self) -> int:
        return len(self._index)

    def get(self, key: str) -> LLMResponse | None:
        return self._index.get(key)

    def put(self, key: str, request: LLMRequest, response: LLMResponse) -> None:
        with self._lock:
            existing = self._index.get(key)
            if existing is not None:
                if existing != response:
                    raise ValueError(f"cassette key {key} already holds a different response")
                return
            self._index[key] = response
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                row = {"key": key, "request": request, "response": response}
                f.write(canonical_json(row) + "\n")
