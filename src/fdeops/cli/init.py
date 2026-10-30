"""``fdeops init``: make a starter tenant folder for your own workflow."""

import re
from importlib import resources
from pathlib import Path

import typer

from fdeops.core.errors import FdeOpsError
from fdeops.packs.registry import available_packs
from fdeops.tenancy.loader import load_tenant

_ID = re.compile(r"^[a-z][a-z0-9-]{1,39}$")
_AGENT_CONFIG = """# Pipeline-test configuration: the rule-based stand-in model.
# Change `provider` and `name` to run a real model (docs/guides/real-model-runs.md).
id: {id}-heuristic
model:
  provider: heuristic
  name: heuristic-{pack}-1
retrieval:
  mode: hybrid
  top_k: 4
  include_superseded: false
"""


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def scaffold(target: Path, pack: str, company: str, tenant_id: str) -> list[Path]:
    """Copy the starter files of a pack into ``target`` and fill in the name."""
    if pack not in available_packs():
        raise FdeOpsError(f"unknown pack {pack!r}; available: {available_packs()}")
    if not _ID.match(tenant_id):
        raise FdeOpsError(
            f"the tenant ID {tenant_id!r} is not valid. Use 2 to 40 characters: "
            "lowercase letters, digits and hyphens, and a letter at the start."
        )
    if target.exists() and any(target.iterdir()):
        raise FdeOpsError(f"{target} is not empty. Select a new folder.")
    source = resources.files("fdeops") / "templates" / pack
    written: list[Path] = []

    def copy(node: "resources.abc.Traversable", dest: Path) -> None:
        if node.is_dir():
            for child in node.iterdir():
                copy(child, dest / child.name)
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = node.read_text(encoding="utf-8")
        dest.write_text(text.replace("{{COMPANY}}", company).replace("{{ID}}", tenant_id), "utf-8")
        written.append(dest)

    copy(source, target)
    return sorted(written)


def init(
    directory: Path = typer.Argument(..., help="The new tenant folder, for example tenants/acme"),
    pack: str = typer.Option("billing", help="Domain pack: billing or logistics"),
    name: str = typer.Option(..., help="The company name, for example 'Acme Billing'"),
    tenant_id: str | None = typer.Option(None, "--id", help="Tenant ID (default: from the name)"),
) -> None:
    """Make a starter tenant: policy, knowledge base, gates, monitors and datasets."""
    tid = tenant_id or slugify(name)
    try:
        files = scaffold(directory, pack, name, tid)
        configs = directory.parent.parent / "configs" / "agents"
        agent = configs / f"{tid}-heuristic.yaml"
        if configs.is_dir() and not agent.exists():
            agent.write_text(_AGENT_CONFIG.format(id=tid, pack=pack), encoding="utf-8")
            typer.echo(f"wrote {agent}")
        tenant = load_tenant(directory)
    except FdeOpsError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1) from e
    typer.echo(f"made tenant {tenant.id} in {directory} ({len(files)} files, pack {pack})")
    typer.echo("Next steps:")
    typer.echo(f"  1. Edit {directory}/policy.yaml and the articles in {directory}/kb/.")
    typer.echo(f"  2. uv run fdeops tenant validate {directory}")
    typer.echo(f"  3. uv run fdeops dataset build --tenant {directory}")
    typer.echo("  4. Refer to docs/guides/test-your-own-agent.md to test your own agent.")
