"""File writes that a crash or a second writer cannot damage."""

import contextlib
import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    """Write ``text`` to ``path`` so that a reader sees the old file or the whole new file.

    The text goes to a temporary file with a unique name in the same folder. The function makes
    sure that the bytes are on the disk, and then it renames the file. A rename in one folder is
    atomic. If the write fails, the old file stays and the temporary file is removed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise
