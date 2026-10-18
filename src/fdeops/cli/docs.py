from pathlib import Path

import typer

from fdeops.devtools.ste import check_paths, load_rules

app = typer.Typer(help="Documentation tools.", no_args_is_help=True)


@app.command("check")
def check(
    paths: list[Path] = typer.Argument(..., help="Markdown files or folders"),
    allow: Path | None = typer.Option(None, help="More technical words, one in each line"),
) -> None:
    """Check Markdown files against the ASD-STE100 rules that a program can find."""
    findings = check_paths(paths, load_rules(allow))
    for f in findings:
        typer.echo(str(f))
    typer.echo(f"{len(findings)} STE finding(s)")
    if findings:
        raise typer.Exit(1)
