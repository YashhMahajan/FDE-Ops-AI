"""The migrations make the same schema as the models, on SQLite and (in CI) on Postgres."""

import os
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from fdeops.storage.db import Base, Database


def _url(tmp_path: Path, name: str) -> str:
    return os.environ.get("FDEOPS_TEST_DATABASE_URL") or f"sqlite:///{tmp_path / name}"


def test_migrations_match_the_models(tmp_path: Path) -> None:
    db = Database(_url(tmp_path, "m.db"))
    db.reset()
    with db.engine.connect() as conn:
        diff = compare_metadata(
            MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata
        )
    assert diff == [], "a model changed without a migration: run alembic revision --autogenerate"
    db.dispose()


def test_migrate_is_safe_to_run_again(tmp_path: Path) -> None:
    db = Database(_url(tmp_path, "again.db"))
    db.reset()
    db.migrate()
    db.migrate()
    with db.engine.connect() as conn:
        version = conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
    assert version == "0001"
    db.dispose()


def test_database_from_before_migrations_gets_a_stamp(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    legacy = Database(url)
    Base.metadata.create_all(legacy.engine)  # the schema of version 2.0.0, without Alembic
    legacy.migrate()
    with legacy.engine.connect() as conn:
        assert "alembic_version" in inspect(conn).get_table_names()
        assert conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == "0001"
    legacy.dispose()
