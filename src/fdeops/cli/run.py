from pathlib import Path

import typer

from fdeops.agent.config import load_agent_config
from fdeops.cli.common import build_llm, load_external_agent, parse_rates
from fdeops.core.errors import FdeOpsError
from fdeops.eval.compare import compare_runs, render_comparison
from fdeops.eval.incidents import load_incident
from fdeops.eval.report import load_run, render_markdown, save_run, summarize
from fdeops.eval.runner import run_eval
from fdeops.llm.types import LLMMode
from fdeops.tenancy.loader import load_tenant
from fdeops.world.dataset import load_dataset


def run(
    tenant: Path = typer.Option(..., help="Tenant directory"),
    agent: Path = typer.Option(..., help="Agent config YAML"),
    dataset: Path = typer.Option(..., help="Built dataset directory (fdeops dataset build)"),
    split: str = typer.Option("test", help="dev or test"),
    trials: int = typer.Option(1, min=1),
    llm_mode: LLMMode = typer.Option(LLMMode.LIVE, "--llm-mode"),
    cassettes: Path | None = typer.Option(None, help="Cassette JSONL for record/replay"),
    model: str | None = typer.Option(None, help="Override the model name in the agent config"),
    provider: str | None = typer.Option(
        None, help="Override the provider (heuristic, openrouter, vllm, ollama, custom)"
    ),
    base_url: str | None = typer.Option(None, help="Override the provider base URL"),
    heuristic_errors: str = typer.Option("", help="e.g. wrong_amount=0.2,miss_escalation=0.1"),
    workers: int = typer.Option(4, min=1),
    incident: Path | None = typer.Option(None, help="An incident file (incidents/<tenant>/*.yaml)"),
    external: str | None = typer.Option(
        None, help="An external Python agent: path/to/file.py:function"
    ),
    out: Path = typer.Option(Path("runs"), help="Where run artifacts are written"),
) -> None:
    """Evaluate an agent configuration on a dataset split."""
    try:
        t = load_tenant(tenant)
        config = load_agent_config(agent)
        overrides = {k: v for k, v in {"name": model, "provider": provider}.items() if v}
        if overrides:
            config = config.model_copy(update={"model": config.model.model_copy(update=overrides)})
        ds = load_dataset(dataset, split)  # type: ignore[arg-type]
        settings = {"error_rates": parse_rates(heuristic_errors)} if heuristic_errors else {}
        agent_fn = load_external_agent(external) if external else None
        llm = None
        if agent_fn is None:
            llm = build_llm(
                t,
                config.model.provider,
                config.model.name,
                llm_mode,
                cassettes,
                base_url,
                settings,
            )
        spec = load_incident(incident) if incident else None
        result = run_eval(
            t,
            config,
            ds,
            llm,
            trials=trials,
            max_workers=workers,
            llm_mode=llm_mode.value,
            llm_settings=settings,
            incident=spec,
            external_agent=agent_fn,
        )
    except FdeOpsError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1) from e
    path = save_run(result, out)
    s = summarize(result)
    typer.echo(
        f"[{s.provenance.value}] {s.run_id}: success {s.overall.rate:.1%} "
        f"(95% CI {s.overall.ci_lo:.1%}-{s.overall.ci_hi:.1%}, n={s.overall.n}), "
        f"critical trials {s.critical_trials}"
    )
    typer.echo(f"report: {path / 'report.md'}")


def report(run_dir: Path) -> None:
    """Print a run's markdown report."""
    typer.echo(render_markdown(summarize(load_run(run_dir))))


def compare(run_a: Path, run_b: Path) -> None:
    """Paired comparison of two runs on the same dataset (B relative to A)."""
    try:
        typer.echo(render_comparison(compare_runs(load_run(run_a), load_run(run_b))))
    except FdeOpsError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1) from e


def incidents(folder: Path = typer.Argument(Path("incidents"))) -> None:
    """List the incident files in a folder."""
    for path in sorted(folder.rglob("*.yaml")):
        spec = load_incident(path)
        typer.echo(f"{path}: [{spec.kind}] {spec.id}: {spec.description}")
