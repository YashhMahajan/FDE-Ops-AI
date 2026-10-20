"""Evaluation regression in CI: replay recorded model calls and check a minimum quality.

A replay costs nothing and gives the same model outputs. If the code of the agent, the prompt or
the evaluators changes, the check shows the effect. A prompt change needs a new recording, because
the requests change and the cassette has no response for them.
"""

from pathlib import Path

import typer

from fdeops.agent.config import load_agent_config
from fdeops.cli.common import build_llm
from fdeops.core.config import load_model
from fdeops.core.errors import FdeOpsError
from fdeops.core.model import FrozenModel
from fdeops.eval.report import summarize
from fdeops.eval.runner import run_eval
from fdeops.llm.types import LLMMode
from fdeops.tenancy.loader import load_tenant


class RegressionCheck(FrozenModel):
    name: str
    tenant: str
    agent: str
    dataset: str = "support-core"
    split: str = "dev"
    cassettes: str
    min_success_lower: float
    max_critical_trials: int = 0


class RegressionManifest(FrozenModel):
    checks: list[RegressionCheck]


def regress(
    manifest: Path,
    record: bool = typer.Option(False, help="Record the cassettes"),
    skip_missing: bool = typer.Option(False, help="Skip a check that has no cassette file"),
) -> None:
    """Replay each check in the manifest and compare it with its minimum quality."""
    root = manifest.resolve().parent
    failed = 0
    try:
        checks = load_model(manifest, RegressionManifest).checks
        for c in checks:
            t = load_tenant((root / c.tenant).resolve())
            config = load_agent_config((root / c.agent).resolve())
            ds = t.build_datasets(c.dataset)[c.split]
            mode = LLMMode.REPLAY_OR_RECORD if record else LLMMode.REPLAY
            cassette = (root / c.cassettes).resolve()
            if skip_missing and not record and not cassette.exists():
                typer.echo(f"skip  {c.name}: no cassette at {c.cassettes}. Record it first.")
                continue
            llm = build_llm(t, config.model.provider, config.model.name, mode, cassette, None, {})
            s = summarize(run_eval(t, config, ds, llm, llm_mode=mode.value))
            ok = (
                s.overall.ci_lo >= c.min_success_lower
                and s.critical_trials <= c.max_critical_trials
            )
            failed += not ok
            typer.echo(
                f"{'pass' if ok else 'fail'}  {c.name}: success {s.overall.rate:.1%}, "
                f"lower limit {s.overall.ci_lo:.1%} (minimum {c.min_success_lower:.0%}), "
                f"critical trials {s.critical_trials}"
            )
    except FdeOpsError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(1) from e
    if failed:
        raise typer.Exit(1)
