from pathlib import Path

import typer

from fdeops.cli.common import build_llm
from fdeops.core.errors import FdeOpsError
from fdeops.diagnose.interventions import diagnose_run
from fdeops.diagnose.report import save_diagnosis
from fdeops.eval.report import load_run
from fdeops.llm.types import LLMMode
from fdeops.tenancy.loader import load_tenant
from fdeops.world.dataset import load_dataset


def diagnose(
    run_dir: Path = typer.Argument(..., help="A run folder from fdeops run"),
    tenant: Path = typer.Option(..., help="Tenant directory"),
    dataset: Path = typer.Option(..., help="The dataset directory of the run"),
    allow_test: bool = typer.Option(False, help="Accept interventions on the test split"),
    llm_mode: LLMMode = typer.Option(LLMMode.LIVE, "--llm-mode"),
    cassettes: Path | None = typer.Option(None),
    base_url: str | None = typer.Option(None),
    max_control: int = typer.Option(20, min=0, help="Passing cases to check for regressions"),
) -> None:
    """Classify failures, cluster them and test causes with counterfactual replay."""
    try:
        run = load_run(run_dir)
        t = load_tenant(tenant)
        ds = load_dataset(dataset, run.dataset_split)  # type: ignore[arg-type]
        llm = build_llm(
            t,
            run.llm_provider,
            run.agent_config.model.name,
            llm_mode,
            cassettes,
            base_url,
            run.llm_settings,
        )
        result = diagnose_run(t, run, ds, llm, allow_test=allow_test, max_control=max_control)
    except FdeOpsError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1) from e
    path = save_diagnosis(result, run_dir)
    typer.echo(f"{result.n_failures} failed trial(s) in {len(result.clusters)} cluster(s).")
    for c in result.clusters:
        typer.echo(
            f"  {c.cluster.id}: {c.verdict.value}"
            + (f", fix {c.recommended_fix}" if c.recommended_fix else "")
        )
    typer.echo(f"report: {path}")
