from pathlib import Path

import typer

from fdeops.core.errors import FdeOpsError
from fdeops.eval.report import load_run
from fdeops.monitor.report import monitor_runs, render_monitor, save_monitor
from fdeops.tenancy.loader import load_tenant


def monitor(
    reference: Path = typer.Argument(..., help="The run folder of the reference window"),
    current: Path = typer.Argument(..., help="The run folder of the current window"),
    tenant: Path = typer.Option(..., help="Tenant directory (with monitors.yaml)"),
    out: Path | None = typer.Option(None, help="Folder for monitor.md and monitor.json"),
) -> None:
    """Compare production signals of two windows. Exit code 2 means one or more page alerts."""
    try:
        t = load_tenant(tenant)
        rep = monitor_runs(t, load_run(reference), load_run(current))
    except FdeOpsError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1) from e
    save_monitor(rep, out or current)
    typer.echo(render_monitor(rep))
    if any(a.severity == "page" for a in rep.alerts):
        raise typer.Exit(2)
