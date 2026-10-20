from pathlib import Path

import typer

from fdeops.agent.config import load_agent_config
from fdeops.cli.common import build_llm
from fdeops.core.errors import FdeOpsError
from fdeops.demo.export import export_demo
from fdeops.demo.flagship import load_flagship_incident, run_flagship
from fdeops.eval.incidents import load_incident
from fdeops.llm.types import LLMMode
from fdeops.tenancy.loader import load_tenant


def demo(
    tenant: Path = typer.Option(Path("tenants/ledgerloop")),
    agent: Path | None = typer.Option(None, help="Agent config (default: the heuristic config)"),
    incident: Path | None = typer.Option(None, help="Incident file (default: the drift incident)"),
    out: Path = typer.Option(Path("demo-output")),
    export: Path | None = typer.Option(None, help="Write JSON for the web UI to this folder"),
    llm_mode: LLMMode = typer.Option(LLMMode.LIVE, "--llm-mode"),
    cassettes: Path | None = typer.Option(None),
    provider: str | None = typer.Option(None, help="Override the provider (for a real model)"),
    model: str | None = typer.Option(None, help="Override the model name"),
    base_url: str | None = typer.Option(None, help="Override the provider URL"),
) -> None:
    """Run the flagship demo: incident, diagnosis, gated fix, approval, ROI and roadmap."""
    try:
        t = load_tenant(tenant)
        root = tenant.resolve().parent.parent
        cfg_path = agent or root / "configs" / "agents" / f"{t.id}-heuristic.yaml"
        config = load_agent_config(cfg_path)
        overrides = {k: v for k, v in {"provider": provider, "name": model}.items() if v}
        if overrides:
            config = config.model_copy(update={"model": config.model.model_copy(update=overrides)})
        spec = load_incident(incident) if incident else load_flagship_incident(root, t)
        llm = build_llm(
            t, config.model.provider, config.model.name, llm_mode, cassettes, base_url, {}
        )
        res = run_flagship(t, config, llm, spec, out / t.id)
        if export is not None:
            export_demo(res, export / t.id)
    except FdeOpsError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1) from e
    for s in res.steps:
        typer.echo(f"[{s.key}] {s.title}: {s.text}")
    typer.echo(f"reports: {out / t.id}")
    if export is not None:
        typer.echo(f"web data: {export / t.id}")
