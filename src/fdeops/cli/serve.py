"""Commands to operate the service. They do not run in tests or on a laptop by default."""

import os

import typer

from fdeops.storage.db import Database
from fdeops.storage.keys import KeyStore, Role

keys_app = typer.Typer(help="API keys.", no_args_is_help=True)
db_app = typer.Typer(help="The database.", no_args_is_help=True)


def _db() -> Database:
    return Database(os.environ.get("FDEOPS_DATABASE_URL", "sqlite:///fdeops.db"))


@db_app.command("init")
def db_init() -> None:
    """Make the tables (the command does nothing to tables that exist)."""
    _db().init()
    typer.echo("database ready")


@keys_app.command("create")
def keys_create(
    name: str = typer.Option(...),
    role: Role = typer.Option(...),
    tenant: str | None = typer.Option(None, help="Omit only for an admin key"),
) -> None:
    """Make an API key. The command shows the key one time."""
    db = _db()
    db.init()
    with db.session() as s:
        secret, row = KeyStore(s).create(tenant, name, role)
    typer.echo(f"{row.key_id} {row.role} tenant={row.tenant_id or '*'}")
    typer.echo(f"key: {secret}")
    typer.echo("Keep the key in a secret store. The service keeps only its hash.")


@keys_app.command("list")
def keys_list(tenant: str | None = typer.Option(None)) -> None:
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
    db = _db()
    with db.session() as s:
        KeyStore(s).revoke(key_id)
    typer.echo(f"{key_id} revoked")


def serve(host: str = typer.Option("0.0.0.0"), port: int = typer.Option(8000)) -> None:
    """Start the API service (uvicorn). Settings come from FDEOPS_* environment variables."""
    import uvicorn

    from fdeops.api.app import create_app

    uvicorn.run(create_app(), host=host, port=port)


def worker(name: str = typer.Option("worker-1"), idle: float = typer.Option(2.0)) -> None:
    """Start a job worker. Run more than one for more throughput."""
    from fdeops.api.app import Settings
    from fdeops.jobs.handlers import Context, handlers
    from fdeops.jobs.queue import JobQueue
    from fdeops.jobs.worker import Worker
    from fdeops.storage.artifacts import LocalArtifactStore

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
    Worker(JobQueue(db), handlers(ctx), name=name).run_forever(idle)
