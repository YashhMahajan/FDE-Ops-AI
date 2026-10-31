"""Commands to operate the service. They do not run in tests or on a laptop by default."""

import os
import signal
import socket
import threading
from typing import TYPE_CHECKING

import typer

from fdeops.storage.roles import Role

if TYPE_CHECKING:
    from fdeops.storage.db import Database

keys_app = typer.Typer(help="API keys.", no_args_is_help=True)
db_app = typer.Typer(help="The database.", no_args_is_help=True)


def _require_server() -> None:
    """The service commands need the server extra. A base install gets a clear message."""
    try:
        import alembic  # noqa: F401
        import fastapi  # noqa: F401
        import sqlalchemy  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError as e:
        typer.echo(
            f"error: this command needs the server extra ({e.name} is missing).\n"
            "Install it with: pip install 'fdeops[server]'",
            err=True,
        )
        raise typer.Exit(1) from e


def _db() -> "Database":
    _require_server()
    from fdeops.storage.db import Database

    return Database(os.environ.get("FDEOPS_DATABASE_URL", "sqlite:///fdeops.db"))


@db_app.command("init")
def db_init() -> None:
    """Bring the schema to the latest migration (safe to run again)."""
    _db().init()
    typer.echo("database ready")


@db_app.command("upgrade")
def db_upgrade(revision: str = typer.Argument("head")) -> None:
    """Run the database migrations up to a revision (default: the latest)."""
    _db().migrate(revision)
    typer.echo(f"database at {revision}")


@db_app.command("revision")
def db_revision(message: str = typer.Option(..., "-m", "--message")) -> None:
    """Make a migration from the changes of the models (for developers)."""
    import tempfile
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    _require_server()
    from fdeops.storage.db import MIGRATIONS, Database

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(f"sqlite:///{Path(tmp) / 'revision.db'}")
        db.migrate()
        cfg = Config()
        cfg.set_main_option("script_location", str(MIGRATIONS))
        with db.engine.begin() as conn:
            cfg.attributes["connection"] = conn
            script = command.revision(cfg, message=message, autogenerate=True)
        db.dispose()
    typer.echo(f"wrote {getattr(script, 'path', script)}. Examine it before you commit it.")


@db_app.command("purge-tenant")
def db_purge_tenant(
    tenant: str = typer.Argument(..., help="The tenant ID"),
    confirm: str = typer.Option(..., help="Type the tenant ID again to confirm"),
) -> None:
    """Delete all data of a tenant (rows, keys, jobs, artifacts). Take a backup first."""
    from pathlib import Path

    _require_server()
    from fdeops.storage.repo import purge_tenant

    if confirm != tenant:
        typer.echo("error: --confirm must be the same as the tenant ID", err=True)
        raise typer.Exit(1)
    artifacts = Path(os.environ.get("FDEOPS_ARTIFACTS_DIR", "artifacts"))
    db = _db()
    with db.session() as s:
        counts = purge_tenant(s, tenant, artifacts)
    for name, n in counts.items():
        typer.echo(f"{name}: {n}")


@keys_app.command("create")
def keys_create(
    name: str = typer.Option(...),
    role: Role = typer.Option(...),
    tenant: str | None = typer.Option(None, help="Omit only for an admin key"),
) -> None:
    """Make an API key. The command shows the key one time."""
    from fdeops.storage.keys import KeyStore

    db = _db()
    db.init()
    with db.session() as s:
        secret, row = KeyStore(s).create(tenant, name, role)
    typer.echo(f"{row.key_id} {row.role} tenant={row.tenant_id or '*'}")
    typer.echo(f"key: {secret}")
    typer.echo("Keep the key in a secret store. The service keeps only its hash.")


@keys_app.command("list")
def keys_list(tenant: str | None = typer.Option(None)) -> None:
    from fdeops.storage.keys import KeyStore

    db = _db()
    db.init()
    with db.session() as s:
        for k in KeyStore(s).list(tenant):
            state = "revoked" if k.revoked_at else "active"
            typer.echo(
                f"{k.key_id} {k.prefix}… {k.role} tenant={k.tenant_id or '*'} {k.name} {state}"
            )


@keys_app.command("revoke")
def keys_revoke(key_id: str) -> None:
    from fdeops.storage.keys import KeyStore

    db = _db()
    with db.session() as s:
        KeyStore(s).revoke(key_id)
    typer.echo(f"{key_id} revoked")


def serve(
    host: str = typer.Option("127.0.0.1", help="Use 0.0.0.0 only in a container"),
    port: int = typer.Option(8000),
) -> None:
    """Start the API service (uvicorn). Settings come from FDEOPS_* environment variables."""
    _require_server()
    import uvicorn

    from fdeops.api.app import create_app

    # server_header=False: the response does not tell the server software.
    # timeout_keep_alive: a client that holds an idle connection cannot keep a slot for long.
    uvicorn.run(create_app(), host=host, port=port, server_header=False, timeout_keep_alive=5)


def worker(
    name: str | None = typer.Option(None, help="Worker name in job leases (default: host name)"),
    idle: float = typer.Option(2.0),
) -> None:
    """Start a job worker. Run more than one for more throughput."""
    _require_server()
    from fdeops.api.app import Settings
    from fdeops.jobs.handlers import Context, handlers
    from fdeops.jobs.queue import JobQueue
    from fdeops.jobs.worker import Worker
    from fdeops.storage.artifacts import LocalArtifactStore
    from fdeops.storage.db import Database

    name = name or socket.gethostname()
    settings = Settings.from_env()
    db = Database(settings.database_url)
    db.init()
    ctx = Context(
        db=db,
        artifacts=LocalArtifactStore(settings.artifacts_dir),
        tenants_dir=settings.tenants_dir,
        configs_dir=settings.configs_dir,
    )
    typer.echo(f"{name}: waiting for jobs")
    stop = threading.Event()

    def _stop(signum: int, _frame: object) -> None:
        typer.echo(f"{name}: signal {signum}, the current job completes, then the worker stops")
        stop.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    Worker(JobQueue(db), handlers(ctx), name=name).run_forever(idle, stop)
