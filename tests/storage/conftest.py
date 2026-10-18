import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from fdeops.storage.db import Database


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    """SQLite by default. CI sets FDEOPS_TEST_DATABASE_URL to run the same tests on Postgres."""
    url = os.environ.get("FDEOPS_TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'fdeops.db'}"
    database = Database(url)
    database.reset()
    yield database
    database.dispose()
