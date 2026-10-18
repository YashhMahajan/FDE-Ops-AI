import typer

from fdeops import __version__
from fdeops.cli import dataset, diagnose, docs, release, run, tenant

app = typer.Typer(
    help="FDE-Ops-AI: evaluate, diagnose and ship AI agents with evidence.", no_args_is_help=True
)
app.add_typer(tenant.app, name="tenant")
app.add_typer(dataset.app, name="dataset")
app.add_typer(docs.app, name="docs")
app.add_typer(release.app, name="release")
app.command("run")(run.run)
app.command("report")(run.report)
app.command("compare")(run.compare)
app.command("diagnose")(diagnose.diagnose)
app.command("incidents")(run.incidents)
app.command("improve")(release.improve)
app.command("shadow")(release.shadow)


@app.command()
def version() -> None:
    """Print the fdeops version."""
    typer.echo(__version__)
