"""A repository with a tenant scope. Each query filters on the tenant, thus a caller cannot read
the data of a different tenant, also by a direct ID."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from fdeops.core.errors import ConfigError, FdeOpsError
from fdeops.eval.report import render_markdown, summarize
from fdeops.eval.runner import RunResult
from fdeops.storage.artifacts import ArtifactStore
from fdeops.storage.db import AnnotationRow, AuditRow, RunRow, TrialRow, utcnow


class NotFound(FdeOpsError):
    """The item is not there, or it belongs to a different tenant. The two cases look the same."""


class Repository:
    def __init__(self, session: Session, tenant_id: str, artifacts: ArtifactStore) -> None:
        self.s = session
        self.tenant_id = tenant_id
        self.artifacts = artifacts

    def save_run(
        self, run: RunResult, primary_failures: dict[tuple[str, int], str] | None = None
    ) -> RunRow:
        if run.tenant_id != self.tenant_id:
            raise ConfigError(f"run {run.run_id} belongs to tenant {run.tenant_id!r}")
        base = f"runs/{self.tenant_id}/{run.run_id}"
        uri = self.artifacts.put_text(f"{base}/run.json", run.model_dump_json())
        summary = summarize(run)
        self.artifacts.put_text(f"{base}/summary.json", summary.model_dump_json(indent=2))
        self.artifacts.put_text(f"{base}/report.md", render_markdown(summary))
        row = RunRow(
            run_id=run.run_id,
            tenant_id=run.tenant_id,
            agent_config_id=run.agent_config.id,
            agent_config_hash=run.agent_config_hash,
            dataset_ref=run.dataset_ref,
            dataset_hash=run.dataset_hash,
            split=run.dataset_split,
            provenance=run.provenance.value,
            llm_provider=run.llm_provider,
            incident_id=run.incident.id if run.incident else None,
            n_trials=len(run.results),
            success_rate=summary.overall.rate,
            started_at=run.started_at.replace(tzinfo=None),
            finished_at=run.finished_at.replace(tzinfo=None),
            artifact_uri=uri,
        )
        self.s.merge(row)
        failures = primary_failures or {}
        for r in run.results:
            self.s.add(
                TrialRow(
                    tenant_id=run.tenant_id,
                    run_id=run.run_id,
                    case_id=r.case_id,
                    trial=r.trial,
                    scenario=r.scenario,
                    tags=list(r.tags),
                    success=r.success,
                    primary_failure=failures.get((r.case_id, r.trial)),
                )
            )
        self.s.flush()
        return row

    def list_runs(self, limit: int = 100) -> list[RunRow]:
        q = (
            select(RunRow)
            .where(RunRow.tenant_id == self.tenant_id)
            .order_by(RunRow.started_at.desc())
            .limit(limit)
        )
        return list(self.s.scalars(q))

    def run_row(self, run_id: str) -> RunRow:
        row = self.s.scalar(
            select(RunRow).where(RunRow.run_id == run_id, RunRow.tenant_id == self.tenant_id)
        )
        if row is None:
            raise NotFound(f"run {run_id} not found")
        return row

    def load_run(self, run_id: str) -> RunResult:
        return RunResult.model_validate_json(
            self.artifacts.get_text(self.run_row(run_id).artifact_uri)
        )

    def report(self, run_id: str) -> str:
        row = self.run_row(run_id)
        return self.artifacts.get_text(row.artifact_uri.replace("run.json", "report.md"))

    def trials(self, run_id: str) -> list[TrialRow]:
        self.run_row(run_id)
        q = (
            select(TrialRow)
            .where(TrialRow.run_id == run_id, TrialRow.tenant_id == self.tenant_id)
            .order_by(TrialRow.id)
        )
        return list(self.s.scalars(q))

    def annotate(
        self, run_id: str, case_id: str, trial: int, rubric: str, label: bool, annotator: str
    ) -> AnnotationRow:
        self.run_row(run_id)
        row = AnnotationRow(
            tenant_id=self.tenant_id,
            run_id=run_id,
            case_id=case_id,
            trial=trial,
            rubric=rubric,
            label=label,
            annotator=annotator,
            created_at=utcnow(),
        )
        self.s.add(row)
        self.s.flush()
        return row

    def human_labels(self, run_id: str, rubric: str) -> dict[str, bool]:
        """The most recent label for each trial (key ``case_id:trial``)."""
        q = (
            select(AnnotationRow)
            .where(
                AnnotationRow.tenant_id == self.tenant_id,
                AnnotationRow.run_id == run_id,
                AnnotationRow.rubric == rubric,
            )
            .order_by(AnnotationRow.id)
        )
        return {f"{a.case_id}:{a.trial}": a.label for a in self.s.scalars(q)}

    def audit(self, actor: str, action: str, target: str, detail: str = "") -> None:
        self.s.add(
            AuditRow(
                tenant_id=self.tenant_id,
                actor=actor,
                action=action,
                target=target,
                detail=detail,
                at=utcnow(),
            )
        )
        self.s.flush()

    def audit_events(self, limit: int = 200) -> list[AuditRow]:
        q = (
            select(AuditRow)
            .where(AuditRow.tenant_id == self.tenant_id)
            .order_by(AuditRow.id.desc())
            .limit(limit)
        )
        return list(self.s.scalars(q))
