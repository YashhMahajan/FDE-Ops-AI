from pathlib import Path

import typer

from fdeops.cli.common import build_llm
from fdeops.core.errors import FdeOpsError
from fdeops.eval.report import load_run
from fdeops.improve.loop import improve as run_improve
from fdeops.llm.types import LLMMode
from fdeops.release.gates import evaluate_gates
from fdeops.release.integration import run_integration_suite
from fdeops.release.memo import render_memo
from fdeops.release.models import GateConfig, Release, load_gates
from fdeops.release.registry import ReleaseRegistry
from fdeops.tenancy.loader import Tenant, load_tenant
from fdeops.world.dataset import load_dataset

app = typer.Typer(
    help="Releases: propose, approve, reject, roll back, status.", no_args_is_help=True
)
REGISTRY = typer.Option(Path("releases"), help="Release registry folder")


def _ctx(tenant: Path, registry: Path) -> tuple[Tenant, GateConfig, ReleaseRegistry]:
    t = load_tenant(tenant)
    return t, load_gates(t.root / "gates.yaml"), ReleaseRegistry(registry, t.id)


def _fail(e: FdeOpsError) -> None:
    typer.echo(f"error: {e}", err=True)
    raise typer.Exit(1) from e


@app.command("propose")
def propose(
    tenant: Path = typer.Option(...),
    candidate: Path = typer.Option(..., help="Run folder of the candidate on the test split"),
    dataset: Path = typer.Option(..., help="Dataset folder (for the integration suite)"),
    version: str = typer.Option(...),
    baseline: Path | None = typer.Option(None, help="Production run folder on the test split"),
    accept_failed_gates: str | None = typer.Option(
        None, help="Only for a first release: accept failed gates and give the reason"
    ),
    registry: Path = REGISTRY,
) -> None:
    """Evaluate the gates of a candidate run and record a release decision."""
    try:
        t, gates, reg = _ctx(tenant, registry)
        cand = load_run(candidate)
        base = load_run(baseline) if baseline else None
        dev = load_dataset(dataset, "dev")
        llm = build_llm(
            t,
            cand.llm_provider,
            cand.agent_config.model.name,
            LLMMode.LIVE,
            None,
            None,
            cand.llm_settings,
        )
        integration = run_integration_suite(t, cand.agent_config, dev, llm, sample=16)
        results = evaluate_gates(
            t, gates, cand, base, integration_passed=integration.passed, regression_passed=True
        )
        notes = ""
        if accept_failed_gates:
            if reg.production() is not None:
                raise FdeOpsError("accept-failed-gates is only for the first release")
            notes = f"Failed gates accepted for the first release: {accept_failed_gates}"
            results = [r.model_copy(update={"passed": True}) for r in results]
        d = reg.propose(
            Release.from_run(t, gates, cand, version),
            cand.run_id,
            base.run_id if base else None,
            results,
            notes=notes,
        )
    except FdeOpsError as e:
        _fail(e)
        return
    typer.echo(f"decision {d.decision_id}: {d.status}")
    for g in d.gates:
        typer.echo(f"  {g.gate}: {g.status} ({g.observed})")


@app.command("approve")
def approve(
    decision: str,
    tenant: Path = typer.Option(...),
    approver: str = typer.Option(...),
    role: str = typer.Option(...),
    comment: str = typer.Option(""),
    registry: Path = REGISTRY,
) -> None:
    """Approve a decision that waits for approval. Production moves to the release."""
    try:
        _, gates, reg = _ctx(tenant, registry)
        d = reg.approve(decision, approver, role, comment, gates.approver_roles)
    except FdeOpsError as e:
        _fail(e)
        return
    typer.echo(f"{d.decision_id}: approved. Production: {d.release.version}")


@app.command("reject")
def reject(
    decision: str,
    tenant: Path = typer.Option(...),
    approver: str = typer.Option(...),
    role: str = typer.Option(...),
    comment: str = typer.Option(""),
    registry: Path = REGISTRY,
) -> None:
    """Reject a decision that waits for approval."""
    try:
        _, gates, reg = _ctx(tenant, registry)
        d = reg.reject(decision, approver, role, comment, gates.approver_roles)
    except FdeOpsError as e:
        _fail(e)
        return
    typer.echo(f"{d.decision_id}: rejected")


@app.command("rollback")
def rollback(
    tenant: Path = typer.Option(...),
    approver: str = typer.Option(...),
    role: str = typer.Option(...),
    reason: str = typer.Option(...),
    registry: Path = REGISTRY,
) -> None:
    """Move production back to the previous release."""
    try:
        _, gates, reg = _ctx(tenant, registry)
        current = reg.rollback(approver, role, reason, gates.approver_roles)
    except FdeOpsError as e:
        _fail(e)
        return
    typer.echo(f"production: {current.version} ({current.release_id})")


@app.command("status")
def status(tenant: Path = typer.Option(...), registry: Path = REGISTRY) -> None:
    """Show production, the decisions and the history."""
    _, _, reg = _ctx(tenant, registry)
    prod = reg.production()
    typer.echo(f"production: {prod.version if prod else 'none'}")
    for d in reg.decisions():
        typer.echo(f"  {d.decision_id} {d.release.version}: {d.status}")
    for e in reg.history():
        typer.echo(f"  {e.at:%Y-%m-%d %H:%M} {e.action} {e.version} by {e.actor} ({e.role})")


@app.command("memo")
def memo(decision: str, tenant: Path = typer.Option(...), registry: Path = REGISTRY) -> None:
    """Print the decision memo."""
    _, _, reg = _ctx(tenant, registry)
    typer.echo(render_memo(reg.decision(decision)))


def improve(
    tenant: Path = typer.Option(...),
    dev_run: Path = typer.Option(..., help="A run folder on the dev split"),
    dataset: Path = typer.Option(..., help="The dataset folder of the run"),
    version: str = typer.Option(..., help="The version label of the candidate release"),
    baseline_test_run: Path | None = typer.Option(
        None, help="Production run on the test split (default: the run of the production release)"
    ),
    out: Path = typer.Option(Path("runs")),
    registry: Path = REGISTRY,
) -> None:
    """Diagnose, fix, validate and propose a release. It stops before production."""
    try:
        t, gates, reg = _ctx(tenant, registry)
        dev = load_run(dev_run)
        if baseline_test_run is None:
            prod_run = reg.production_run_id
            if prod_run is None:
                raise FdeOpsError("there is no production release. Give --baseline-test-run")
            baseline_test_run = out / prod_run
        base = load_run(baseline_test_run)
        llm = build_llm(
            t,
            dev.llm_provider,
            dev.agent_config.model.name,
            LLMMode.LIVE,
            None,
            None,
            dev.llm_settings,
        )
        result = run_improve(
            t,
            gates,
            reg,
            dev,
            load_dataset(dataset, "dev"),
            load_dataset(dataset, "test"),
            base,
            llm,
            version,
            runs_dir=out,
        )
    except FdeOpsError as e:
        _fail(e)
        return
    typer.echo(f"improvement {result.proposal_id}: {result.status}")
    if result.intervention_id:
        typer.echo(f"  fix: {result.intervention_id} for {result.cluster_id}")
    if result.decision_id:
        typer.echo(f"  decision {result.decision_id}")
    for n in result.notes:
        typer.echo(f"  {n}")


def shadow(
    tenant: Path = typer.Option(...),
    dataset: Path = typer.Option(...),
    production: Path = typer.Option(..., help="Agent config of production"),
    candidate: Path = typer.Option(..., help="Agent config of the candidate"),
    split: str = typer.Option("dev"),
) -> None:
    """Run the candidate next to production on the same traffic, without gates."""
    from fdeops.agent.config import load_agent_config
    from fdeops.release.shadow import shadow_compare

    try:
        t = load_tenant(tenant)
        prod_cfg, cand_cfg = load_agent_config(production), load_agent_config(candidate)
        llm = build_llm(
            t, prod_cfg.model.provider, prod_cfg.model.name, LLMMode.LIVE, None, None, {}
        )
        report = shadow_compare(
            t,
            load_dataset(dataset, split),  # type: ignore[arg-type]
            prod_cfg,
            cand_cfg,
            llm,
        )
    except FdeOpsError as e:
        _fail(e)
        return
    typer.echo(
        f"agreement {report.agreement:.1%} on {report.n_cases} cases. Success: "
        f"production {report.production_success:.1%}, candidate "
        f"{report.candidate_success:.1%}"
    )
    for d in report.disagreements[:20]:
        typer.echo(
            f"  {d.case_id} {d.scenario}: production {d.production_resolution} "
            f"({'pass' if d.production_success else 'fail'}), candidate "
            f"{d.candidate_resolution} ({'pass' if d.candidate_success else 'fail'})"
        )
