from pathlib import Path

import typer

from fdeops.tenancy.loader import load_tenant
from fdeops.world.dataset import save_dataset

app = typer.Typer(help="Datasets.", no_args_is_help=True)


@app.command("build")
def build(
    tenant: Path = typer.Option(..., help="Tenant directory, e.g. tenants/ledgerloop"),
    out: Path = typer.Option(Path("data/datasets"), help="Output root"),
    name: str | None = typer.Option(None, help="Dataset name (default: all in tenant.yaml)"),
) -> None:
    """Generate versioned datasets with oracle ground truth."""
    t = load_tenant(tenant)
    names = [name] if name else [s.name for s in t.config.datasets]
    for n in names:
        for _split, ds in t.build_datasets(n).items():
            path = save_dataset(ds, out)
            typer.echo(f"{ds.ref}: {len(ds.cases)} cases {ds.content_hash} -> {path}")
