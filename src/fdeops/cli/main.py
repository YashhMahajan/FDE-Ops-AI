import typer

from fdeops import __version__
from fdeops.cli import (
    dataset,
    demo,
    diagnose,
    docs,
    impact,
    monitor,
    regress,
    release,
    run,
    serve,
    tenant,
)

app = typer.Typer(
    help="FDE-Ops-AI: evaluate, diagnose and ship AI agents with evidence.", no_args_is_help=True
)
app.add_typer(tenant.app, name="tenant")
app.add_typer(dataset.app, name="dataset")
app.add_typer(docs.app, name="docs")
app.add_typer(release.app, name="release")
app.add_typer(serve.keys_app, name="keys")
app.add_typer(serve.db_app, name="db")
app.command("serve")(serve.serve)
app.command("worker")(serve.worker)
app.command("run")(run.run)
app.command("report")(run.report)
app.command("compare")(run.compare)
app.command("diagnose")(diagnose.diagnose)
app.command("incidents")(run.incidents)
app.command("improve")(release.improve)
app.command("shadow")(release.shadow)
app.command("baseline")(impact.baseline)
app.command("impact")(impact.impact)
app.command("opportunities")(impact.opportunities)
app.command("demo")(demo.demo)
app.command("regress")(regress.regress)
app.command("monitor")(monitor.monitor)


@app.command()
def version() -> None:
    """Print the fdeops version."""
    typer.echo(__version__)
