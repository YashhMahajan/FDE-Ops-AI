import typer

from fdeops import __version__
from fdeops.cli import dataset, run, tenant

app = typer.Typer(
    help="FDE-Ops-AI: evaluate, diagnose and ship AI agents with evidence.", no_args_is_help=True
)
app.add_typer(tenant.app, name="tenant")
app.add_typer(dataset.app, name="dataset")
app.command("run")(run.run)
app.command("report")(run.report)
app.command("compare")(run.compare)


@app.command()
def version() -> None:
    """Print the fdeops version."""
    typer.echo(__version__)
