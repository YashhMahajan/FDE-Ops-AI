"""Shared CLI helpers: build the model client that a run or a diagnosis needs."""

from pathlib import Path
from typing import Any

from fdeops.core.errors import FdeOpsError
from fdeops.llm.cassette import CassetteStore
from fdeops.llm.presets import PRESETS, build_provider
from fdeops.llm.recording import RecordingClient
from fdeops.llm.retrying import RetryingLLM
from fdeops.llm.types import LLMClient, LLMMode
from fdeops.tenancy.loader import Tenant


def parse_rates(spec: str) -> dict[str, float]:
    out = {}
    for part in filter(None, (p.strip() for p in spec.split(","))):
        name, _, value = part.partition("=")
        out[name] = float(value)
    return out


def build_llm(
    tenant: Tenant,
    provider: str,
    model: str,
    mode: LLMMode,
    cassettes: Path | None,
    base_url: str | None,
    settings: dict[str, Any],
) -> LLMClient:
    if mode == LLMMode.REPLAY:
        if cassettes is None or not cassettes.exists():
            raise FdeOpsError(f"replay mode needs an existing cassette file (got {cassettes})")
        return RecordingClient(None, CassetteStore(cassettes), mode, provider_name=provider)
    inner: LLMClient
    if provider == "heuristic":
        inner = tenant.pack.heuristic_model(seed=0, error_rates=settings.get("error_rates", {}))
    elif provider in PRESETS:
        inner = RetryingLLM(build_provider(provider, model, base_url=base_url))
    else:
        raise FdeOpsError(
            f"unknown provider {provider!r}; use heuristic or one of {sorted(PRESETS)}"
        )
    if mode == LLMMode.LIVE:
        return inner
    if cassettes is None:
        raise FdeOpsError(f"mode {mode} needs --cassettes")
    return RecordingClient(inner, CassetteStore(cassettes), mode, provider_name=provider)
