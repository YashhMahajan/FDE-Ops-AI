from pathlib import Path


class FdeOpsError(Exception):
    """Base class for all errors raised by fdeops."""


class ConfigError(FdeOpsError):
    """Invalid or unreadable configuration. Always names the offending file when there is one."""

    def __init__(self, message: str, path: Path | None = None) -> None:
        self.message = message
        self.path = path
        super().__init__(f"{path}: {message}" if path is not None else message)
