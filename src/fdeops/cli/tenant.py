from pathlib import Path

import typer

from fdeops.tenancy.loader import load_tenant

app = typer.Typer(help="Tenant configuration.", no_args_is_help=True)


@app.command("validate")
def validate(root: Path) -> None:
    """Load a tenant directory and report what it contains."""
    t = load_tenant(root)
    typer.echo(f"tenant {t.id} ({t.config.display_name}) pack={t.pack.id}")
    typer.echo(f"  kb: {len(t.kb.keys())} sections, {len(t.kb.sections)} section versions")
    typer.echo(
        f"  world: {sum(len(t.base_world.collection(c)) for c in t.base_world.collection_names())}"
        " entities"
    )
    q = t.data_quality
    typer.echo(
        f"  data quality: {sum(q.loaded.values())} records loaded, "
        f"{sum(q.quarantined.values())} isolated, {len(q.issues)} issue(s)"
    )
    for spec in t.config.datasets:
        typer.echo(
            f"  dataset {spec.name}@v{spec.version}: {sum(spec.cases_per_scenario.values())} cases"
        )
