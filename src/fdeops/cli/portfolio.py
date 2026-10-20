import tempfile
from pathlib import Path

import typer

from fdeops.agent.config import load_agent_config
from fdeops.core.errors import FdeOpsError
from fdeops.demo.flagship import DemoResult, load_flagship_incident, run_flagship
from fdeops.demo.portfolio import write_portfolio
from fdeops.tenancy.loader import load_tenant


def portfolio(
    tenants: list[Path] = typer.Option(
        [Path("tenants/ledgerloop"), Path("tenants/parcelpoint")],
        "--tenant",
        help="Tenant directories. The second tenant is the subject of the case study.",
    ),
    out: Path = typer.Option(Path("docs/portfolio/generated")),
) -> None:
    """Run the flagship demo for each tenant and write the generated portfolio documents."""
    results: list[DemoResult] = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for path in tenants:
                t = load_tenant(path)
                root = path.resolve().parent.parent
                config = load_agent_config(root / "configs" / "agents" / f"{t.id}-heuristic.yaml")
                llm = t.pack.heuristic_model(0, {})
                incident = load_flagship_incident(root, t)
                results.append(run_flagship(t, config, llm, incident, Path(tmp) / t.id))
            repo_root = tenants[0].resolve().parent.parent
            written = write_portfolio(results, repo_root, out)
    except FdeOpsError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1) from e
    for p in written:
        typer.echo(f"wrote {p}")
