from typing import Literal

from fdeops.core.model import FrozenModel

Severity = Literal["critical", "major", "minor"]


class Violation(FrozenModel):
    rule: str
    severity: Severity
    message: str
    op: str | None = None
