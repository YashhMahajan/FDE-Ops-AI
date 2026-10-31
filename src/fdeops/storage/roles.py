"""API roles. This module has no third-party imports.

Thus, the CLI can use it without the server extra.
"""

from enum import StrEnum


class Role(StrEnum):
    VIEWER = "viewer"
    ENGINEER = "engineer"
    APPROVER = "approver"
    ADMIN = "admin"

    @property
    def rank(self) -> int:
        return ["viewer", "engineer", "approver", "admin"].index(self.value)

    def allows(self, required: "Role") -> bool:
        return self.rank >= required.rank
