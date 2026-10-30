"""``fdeops doctor``: check that this machine is ready to use the platform."""

import importlib.util
import os
import shutil
import sys
from pathlib import Path

import typer

from fdeops import __version__
from fdeops.core.errors import FdeOpsError
from fdeops.tenancy.loader import load_tenant

OK, WARN, FAIL = "ok", "warn", "fail"


def _module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def run_checks(
    tenant: Path | None, env: dict[str, str] | None = None
) -> list[tuple[str, str, str]]:
    """Return (status, check, detail) rows. A `fail` row stops the use of the platform."""
    env = dict(os.environ) if env is None else env
    rows: list[tuple[str, str, str]] = []
    py = sys.version_info
    rows.append(
        (
            OK if py >= (3, 11) else FAIL,
            "python",
            f"{py.major}.{py.minor}.{py.micro} (3.11 or newer)",
        )
    )
    rows.append((OK, "fdeops", __version__))
    server = all(_module(m) for m in ("fastapi", "uvicorn", "sqlalchemy", "alembic"))
    rows.append(
        (
            OK if server else WARN,
            "service dependencies",
            "installed" if server else "not installed; run: pip install 'fdeops[server]'",
        )
    )
    key = env.get("OPENROUTER_API_KEY") or env.get("FDEOPS_LLM_API_KEY")
    rows.append(
        (
            OK if key else WARN,
            "model key",
            "set" if key else "not set; the heuristic model and cassette replay need no key",
        )
    )
    docker = shutil.which("docker")
    rows.append(
        (
            OK if docker else WARN,
            "docker",
            "found" if docker else "not found; only the Compose stack needs it",
        )
    )
    data = Path(env.get("FDEOPS_ARTIFACTS_DIR", "data"))
    probe = data if data.exists() else data.parent
    rows.append(
        (
            OK if os.access(probe if probe.exists() else ".", os.W_OK) else FAIL,
            "data folder",
            f"{data} can be written",
        )
    )
    if tenant is not None:
        try:
            t = load_tenant(tenant)
            rows.append(
                (OK, "tenant", f"{t.id}: {len(t.kb.keys())} knowledge sections, pack {t.pack.id}")
            )
        except FdeOpsError as e:
            rows.append((FAIL, "tenant", str(e)))
    return rows


def doctor(
    tenant: Path | None = typer.Option(None, help="Also load and check this tenant folder"),
) -> None:
    """Check Python, dependencies, model key, Docker and an optional tenant folder."""
    rows = run_checks(tenant)
    for status, check, detail in rows:
        typer.echo(f"[{status:>4}] {check}: {detail}")
    failed = sum(1 for s, _, _ in rows if s == FAIL)
    typer.echo(f"{failed} failure(s)")
    if failed:
        raise typer.Exit(1)
