"""Named provider presets. All are free to use: OpenRouter's free models, or open models served
by vLLM (e.g. in a Kaggle notebook) or Ollama. Keys are read from the environment, never from files
in the repository."""

import os
from dataclasses import dataclass, field

import httpx

from fdeops.core.errors import ConfigError
from fdeops.llm.openai_compat import OpenAICompatibleLLM

REPO_URL = "https://github.com/YashhMahajan/FDE-Ops-AI"


@dataclass(frozen=True)
class Preset:
    name: str
    base_url: str
    api_key_env: str | None
    headers: dict[str, str] = field(default_factory=dict)
    key_required: bool = True


PRESETS: dict[str, Preset] = {
    "openrouter": Preset(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        # Optional attribution headers OpenRouter documents for app identification.
        headers={"HTTP-Referer": REPO_URL, "X-Title": "FDE-Ops-AI"},
    ),
    "vllm": Preset(name="vllm", base_url="http://localhost:8000/v1", api_key_env=None),
    "ollama": Preset(name="ollama", base_url="http://localhost:11434/v1", api_key_env=None),
    "custom": Preset(
        name="custom", base_url="", api_key_env="FDEOPS_LLM_API_KEY", key_required=False
    ),
}


def build_provider(
    preset: str,
    model: str,
    base_url: str | None = None,
    timeout_s: float = 120.0,
    transport: httpx.BaseTransport | None = None,
) -> OpenAICompatibleLLM:
    if preset not in PRESETS:
        raise ConfigError(f"unknown LLM preset {preset!r}; choose from {sorted(PRESETS)}")
    p = PRESETS[preset]
    url = base_url or p.base_url
    if not url:
        raise ConfigError(f"preset {preset!r} needs --base-url")
    key = os.environ.get(p.api_key_env) if p.api_key_env else None
    if p.api_key_env and p.key_required and not key:
        raise ConfigError(f"set {p.api_key_env} in your environment to use the {preset} preset")
    return OpenAICompatibleLLM(
        base_url=url,
        model=model,
        api_key=key,
        timeout_s=timeout_s,
        provider=p.name,
        headers=p.headers,
        transport=transport,
    )
