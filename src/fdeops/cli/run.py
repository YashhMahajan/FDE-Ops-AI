from pathlib import Path

import typer

from fdeops.agent.config import load_agent_config
from fdeops.core.errors import FdeOpsError
from fdeops.eval.compare import compare_runs, render_comparison
from fdeops.eval.report import load_run, render_markdown, save_run, summarize
from fdeops.eval.runner import run_eval
from fdeops.llm.cassette import CassetteStore
from fdeops.llm.presets import PRESETS, build_provider
from fdeops.llm.recording import RecordingClient
from fdeops.llm.retrying import RetryingLLM
from fdeops.llm.types import LLMClient, LLMMode
from fdeops.tenancy.loader import Tenant, load_tenant
from fdeops.world.dataset import load_dataset


def _parse_rates(spec: str) -> dict[str, float]:
    out = {}
    for part in filter(None, (p.strip() for p in spec.split(","))):
        name, _, value = part.partition("=")
        out[name] = float(value)
    return out


def _llm(
    tenant: Tenant,
    provider: str,
    model: str,
    mode: LLMMode,
    cassettes: Path | None,
    base_url: str | None,
    heuristic_errors: str,
) -> LLMClient:
    if mode == LLMMode.REPLAY:
        if cassettes is None or not cassettes.exists():
            raise FdeOpsError(f"replay mode needs an existing cassette file (got {cassettes})")
        return RecordingClient(None, CassetteStore(cassettes), mode, provider_name=provider)
    inner: LLMClient
    if provider == "heuristic":
        inner = tenant.pack.heuristic_model(seed=0, error_rates=_parse_rates(heuristic_errors))
    elif provider in PRESETS:
        inner = RetryingLLM(build_provider(provider, model, base_url=base_url))
    else:
        raise FdeOpsError(
            f"unknown provider {provider!r}; use heuristic or one of {sorted(PRESETS)}"
        )
    if mode == LLMMode.LIVE:
        return inner
    if cassettes is None:
        raise FdeOpsError(f"mode {mode} needs --cassettes")
    return RecordingClient(inner, CassetteStore(cassettes), mode, provider_name=provider)


def run(
    tenant: Path = typer.Option(..., help="Tenant directory"),
    agent: Path = typer.Option(..., help="Agent config YAML"),
    dataset: Path = typer.Option(..., help="Built dataset directory (fdeops dataset build)"),
    split: str = typer.Option("test", help="dev or test"),
    trials: int = typer.Option(1, min=1),
    llm_mode: LLMMode = typer.Option(LLMMode.LIVE, "--llm-mode"),
    cassettes: Path | None = typer.Option(None, help="Cassette JSONL for record/replay"),
    model: str | None = typer.Option(None, help="Override the model name in the agent config"),
    base_url: str | None = typer.Option(None, help="Override the provider base URL"),
    heuristic_errors: str = typer.Option("", help="e.g. wrong_amount=0.2,miss_escalation=0.1"),
    workers: int = typer.Option(4, min=1),
    out: Path = typer.Option(Path("runs"), help="Where run artifacts are written"),
) -> None:
    """Evaluate an agent configuration on a dataset split."""
    try:
        t = load_tenant(tenant)
        config = load_agent_config(agent)
        if model:
            config = config.model_copy(
                update={"model": config.model.model_copy(update={"name": model})}
            )
        ds = load_dataset(dataset, split)  # type: ignore[arg-type]
        llm = _llm(
            t,
            config.model.provider,
            config.model.name,
            llm_mode,
            cassettes,
            base_url,
            heuristic_errors,
        )
        result = run_eval(
            t, config, ds, llm, trials=trials, max_workers=workers, llm_mode=llm_mode.value
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
