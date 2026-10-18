"""PII redaction for stored traces, transcripts and scores.

The platform redacts after the evaluators run. The scores use the real text. The stored record
does not keep the personal data. Named patterns: EMAIL, PHONE, CARD. A tenant can add patterns.
"""

import re
from functools import cache
from typing import Any

from fdeops.core.model import FrozenModel

NAMED = {
    "EMAIL": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "CARD": r"\b(?:\d[ -]?){12,18}\d\b",
    # A phone number has a "+" or a parenthesized area code, or digit groups with separators.
    # Plain digit runs (IDs, amounts, dates) do not match.
    "PHONE": r"(?:\+\d{1,3}[ .-]?)?(?:\(\d{2,4}\)[ .-]?)\d{3}[ .-]\d{4}\b"
    r"|\+\d{1,3}[ .-]\d{2,4}[ .-]\d{3}[ .-]\d{3,4}\b",
}


class PIIConfig(FrozenModel):
    redact: bool = False
    patterns: tuple[str, ...] = ("EMAIL", "CARD", "PHONE")
    custom: dict[str, str] = {}


@cache
def _compiled(
    patterns: tuple[str, ...], custom: tuple[tuple[str, str], ...]
) -> list[tuple[str, re.Pattern[str]]]:
    out = [(name, re.compile(NAMED[name])) for name in patterns]
    out += [(name, re.compile(rx)) for name, rx in custom]
    return out


def redact_text(text: str, cfg: PIIConfig) -> str:
    for name, rx in _compiled(cfg.patterns, tuple(sorted(cfg.custom.items()))):
        text = rx.sub(f"[{name}]", text)
    return text


def redact_value(value: Any, cfg: PIIConfig) -> Any:
    if isinstance(value, str):
        return redact_text(value, cfg)
    if isinstance(value, dict):
        return {k: redact_value(v, cfg) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact_value(v, cfg) for v in value]
    return value
