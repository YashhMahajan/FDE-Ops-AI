from typing import Any


def normalize_email(row: dict[str, Any]) -> dict[str, Any]:
    """Email addresses are not case-sensitive in practice. Remove spaces and use lower case."""
    email = row.get("email")
    if isinstance(email, str):
        return {**row, "email": email.strip().lower()}
    return row
