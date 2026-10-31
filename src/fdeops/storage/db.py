"""Database tables and sessions. The same code runs on SQLite (local) and Postgres (CI, deploy).

Times are stored as UTC without a time zone, because SQLite has no time-zone type. The code
converts at the edges.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class RunRow(Base):
    __tablename__ = "runs"
    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_config_id: Mapped[str] = mapped_column(String(200))
    agent_config_hash: Mapped[str] = mapped_column(String(80))
    dataset_ref: Mapped[str] = mapped_column(String(200))
    dataset_hash: Mapped[str] = mapped_column(String(80))
    split: Mapped[str] = mapped_column(String(10))
    provenance: Mapped[str] = mapped_column(String(40))
    llm_provider: Mapped[str] = mapped_column(String(80))
    incident_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    n_trials: Mapped[int] = mapped_column(Integer)
    success_rate: Mapped[float] = mapped_column(Float)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime] = mapped_column(DateTime)
    artifact_uri: Mapped[str] = mapped_column(String(400))


class TrialRow(Base):
    __tablename__ = "trials"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    case_id: Mapped[str] = mapped_column(String(64))
    trial: Mapped[int] = mapped_column(Integer)
    scenario: Mapped[str] = mapped_column(String(80))
    tags: Mapped[list[str]] = mapped_column(JSON)
    success: Mapped[bool] = mapped_column(Boolean)
    primary_failure: Mapped[str | None] = mapped_column(String(60), nullable=True)


class AnnotationRow(Base):
    __tablename__ = "annotations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    case_id: Mapped[str] = mapped_column(String(64))
    trial: Mapped[int] = mapped_column(Integer)
    rubric: Mapped[str] = mapped_column(String(80))
    label: Mapped[bool] = mapped_column(Boolean)
    annotator: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditRow(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    actor: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(80))
    target: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ApiKeyRow(Base):
    __tablename__ = "api_keys"
    key_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class JobRow(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


def normalize_url(url: str) -> str:
    """Hosts such as Render and Heroku give ``postgres://`` URLs. SQLAlchemy needs a driver name."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


MIGRATIONS = Path(__file__).parent / "migrations"
FIRST_REVISION = "0001"
MIGRATION_LOCK = 4_242_001


def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
    """WAL: a writer does not block readers, and a crash does not damage the file."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


class Database:
    def __init__(self, url: str) -> None:
        url = normalize_url(url)
        self.url = url
        self.is_sqlite = url.startswith("sqlite")
        kwargs: dict[str, Any] = {
            "future": True,
            # Test a pooled connection before use. After a database restart or a failover, the
            # pool does not hand a dead connection to a request.
            "pool_pre_ping": True,
            # Servers and proxies close idle connections. Replace them before that happens.
            "pool_recycle": 1800,
        }
        if self.is_sqlite:
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        self.engine: Engine = create_engine(url, **kwargs)
        if self.is_sqlite and ":memory:" not in url:
            event.listen(self.engine, "connect", _sqlite_pragmas)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def init(self) -> None:
        """Bring the schema to the latest migration. It is safe to call at each start."""
        self.migrate()

    def migrate(self, revision: str = "head") -> None:
        """Run the Alembic migrations in ``storage/migrations``.

        On Postgres, an advisory lock makes sure that only one process (API or worker) migrates
        at a time. A database from before migrations (tables, but no version) gets the stamp of
        the first revision, because that revision is the same schema.
        """
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import inspect, text

        cfg = Config()
        cfg.set_main_option("script_location", str(MIGRATIONS))
        with self.engine.begin() as conn:
            if conn.dialect.name == "postgresql":
                conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": MIGRATION_LOCK})
            cfg.attributes["connection"] = conn
            tables = set(inspect(conn).get_table_names())
            if "alembic_version" not in tables and "jobs" in tables:
                command.stamp(cfg, FIRST_REVISION)
            command.upgrade(cfg, revision)

    def reset(self) -> None:
        """Drop all tables and migrate again. Only for tests: it deletes all data."""
        from sqlalchemy import text

        Base.metadata.drop_all(self.engine)
        with self.engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        self.migrate()

    @contextmanager
    def session(self) -> Iterator[Session]:
        s = self._sessions()
        try:
            yield s
            s.commit()
        except BaseException:
            s.rollback()
            raise
        finally:
            s.close()

    def dispose(self) -> None:
        self.engine.dispose()
