from functools import cache
from importlib import resources

from fdeops.core.errors import ConfigError
from fdeops.core.hashing import content_hash
from fdeops.core.model import FrozenModel


class PromptTemplate(FrozenModel):
    version: str
    text: str
    hash: str

    def render(self, **fields: str) -> str:
        return self.text.format(**fields)


@cache
def load_prompt(version: str) -> PromptTemplate:
    try:
        text = (resources.files("fdeops.agent") / "prompts" / f"{version}.md").read_text("utf-8")
    except FileNotFoundError:
        raise ConfigError(f"unknown prompt version {version!r}") from None
    return PromptTemplate(version=version, text=text, hash=content_hash(text))
