from pathlib import Path

import typer

from fdeops.agent.config import AgentConfig, ModelRef
from fdeops.core.errors import FdeOpsError
from fdeops.diagnose.report import load_diagnosis
from fdeops.eval.report import load_run, save_run
from fdeops.eval.runner import run_eval
from fdeops.impact.baseline import faq_agent
from fdeops.impact.costs import load_costs
from fdeops.impact.measure import measure_run
from fdeops.impact.report import render_roi
from fdeops.impact.roi import simulate_roi
from fdeops.insights.opportunities import build_opportunities, load_effort
from fdeops.insights.roadmap import render_roadmap
from fdeops.release.models import load_gates
from fdeops.tenancy.loader import load_tenant
from fdeops.world.dataset import load_dataset

FAQ_CONFIG = AgentConfig(id="faq-baseline", model=ModelRef(provider="external", name="faq"))


def _fail(e: FdeOpsError) -> None:
    typer.echo(f"error: {e}", err=True)
    raise typer.Exit(1) from e


def baseline(
    tenant: Path = typer.Option(...),
    dataset: Path = typer.Option(...),
    split: str = typer.Option("test"),
    out: Path = typer.Option(Path("runs")),
) -> None:
    """Run the FAQ baseline (no LLM) on a dataset split."""
    try:
        t = load_tenant(tenant)
        run = run_eval(
            t,
            FAQ_CONFIG,
            load_dataset(dataset, split),  # type: ignore[arg-type]
            None,
            external_agent=faq_agent,
        )
    except FdeOpsError as e:
        _fail(e)
        return
    path = save_run(run, out)
    typer.echo(
        f"baseline run {run.run_id}: {sum(r.success for r in run.results)}/"
        f"{len(run.results)} correct. Report: {path / 'report.md'}"
    )


def impact(
    run_dir: Path,
    tenant: Path = typer.Option(...),
    baseline_run: Path | None = typer.Option(None, help="A run of the FAQ baseline"),
    draws: int = typer.Option(10_000, min=100),
) -> None:
    """Estimate ROI from a run and the tenant cost file, with a Monte Carlo simulation."""
    try:
        t = load_tenant(tenant)
        costs = load_costs(t.root / "costs.yaml")
        pricing = load_gates(t.root / "gates.yaml").pricing
        measured = measure_run(load_run(run_dir), costs, pricing)
        base = measure_run(load_run(baseline_run), costs, pricing) if baseline_run else None
        roi = simulate_roi(measured, costs, draws=draws, baseline=base)
    except FdeOpsError as e:
        _fail(e)
        return
    (run_dir / "impact.json").write_text(roi.model_dump_json(indent=2))
    (run_dir / "impact.md").write_text(render_roi(roi))
    s = roi.monthly_savings_vs_human
    typer.echo(
        f"savings for each month against a person only: median ${s.p50:,.0f} "
        f"(5th to 95th percentile ${s.p5:,.0f} to ${s.p95:,.0f}), probability above zero "
        f"{s.prob_positive:.0%}"
    )
    typer.echo(f"report: {run_dir / 'impact.md'}")


def opportunities(run_dir: Path, tenant: Path = typer.Option(...)) -> None:
    """Rank product opportunities from the diagnosis of a run, and write the roadmap memo."""
    try:
        t = load_tenant(tenant)
        if not (run_dir / "diagnosis.json").exists():
            raise FdeOpsError("the run has no diagnosis. Run 'fdeops diagnose' first")
        costs = load_costs(t.root / "costs.yaml")
        run = load_run(run_dir)
        opps = build_opportunities(
            run,
            load_diagnosis(run_dir),
            measure_run(run, costs, load_gates(t.root / "gates.yaml").pricing),
            costs,
            load_effort(t.root / "effort.yaml"),
        )
    except FdeOpsError as e:
        _fail(e)
        return
    import json

    (run_dir / "opportunities.json").write_text(
        json.dumps([o.model_dump() for o in opps], indent=2)
    )
    (run_dir / "roadmap.md").write_text(render_roadmap(opps, t.id))
    for o in opps:
        typer.echo(f"{o.decision:>9} {o.score:>10,.0f}  {o.cluster_id}  fix={o.fix}")
    typer.echo(f"memo: {run_dir / 'roadmap.md'}")
