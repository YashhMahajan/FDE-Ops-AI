"""The release registry of one tenant, on disk. Each change is an atomic file write.

Only ``approve`` and ``rollback`` move the production pointer, and each needs an approver role.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from fdeops.core.errors import ConfigError
from fdeops.core.ids import new_id
from fdeops.release.models import (
    ApprovalRecord,
    GateResult,
    HistoryEvent,
    Release,
    ReleaseDecision,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class ReleaseRegistry:
    def __init__(self, root: Path, tenant_id: str) -> None:
        self.root = root / tenant_id
        self.tenant_id = tenant_id
        (self.root / "decisions").mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ reads
    def decision(self, decision_id: str) -> ReleaseDecision:
        p = self.root / "decisions" / f"{decision_id}.json"
        if not p.exists():
            raise ConfigError(f"no decision {decision_id!r} for tenant {self.tenant_id!r}")
        return ReleaseDecision.model_validate_json(p.read_text())

    def decisions(self) -> list[ReleaseDecision]:
        items = [
            ReleaseDecision.model_validate_json(p.read_text())
            for p in (self.root / "decisions").glob("*.json")
        ]
        return sorted(items, key=lambda d: d.created_at)

    def _pointer(self) -> dict[str, list[str]]:
        p = self.root / "production.json"
        return json.loads(p.read_text()) if p.exists() else {"stack": []}

    def production(self) -> Release | None:
        stack = self._pointer()["stack"]
        return self._release(stack[-1]) if stack else None

    @property
    def production_run_id(self) -> str | None:
        prod = self.production()
        if prod is None:
            return None
        d = next(
            (
                d
                for d in reversed(self.decisions())
                if d.release.release_id == prod.release_id and d.status == "approved"
            ),
            None,
        )
        return d.candidate_run_id if d else None

    def _release(self, release_id: str) -> Release:
        for d in self.decisions():
            if d.release.release_id == release_id:
                return d.release
        raise ConfigError(f"unknown release {release_id!r}")

    def history(self) -> list[HistoryEvent]:
        p = self.root / "history.jsonl"
        if not p.exists():
            return []
        return [
            HistoryEvent.model_validate_json(line)
            for line in p.read_text().splitlines()
            if line.strip()
        ]

    # ------------------------------------------------------------------ writes
    def _save(self, d: ReleaseDecision) -> ReleaseDecision:
        _write(self.root / "decisions" / f"{d.decision_id}.json", d.model_dump_json(indent=2))
        return d

    def _log(self, event: HistoryEvent) -> None:
        p = self.root / "history.jsonl"
        lines = p.read_text().splitlines() if p.exists() else []
        _write(p, "\n".join([*lines, event.model_dump_json()]) + "\n")

    def propose(
        self,
        release: Release,
        candidate_run_id: str,
        baseline_run_id: str | None,
        gates: list[GateResult],
        notes: str = "",
        regression_cases: tuple[str, ...] = (),
    ) -> ReleaseDecision:
        if release.tenant_id != self.tenant_id:
            raise ConfigError("the release belongs to a different tenant")
        ok = all(g.passed for g in gates)
        return self._save(
            ReleaseDecision(
                decision_id=new_id("dec"),
                tenant_id=self.tenant_id,
                release=release,
                candidate_run_id=candidate_run_id,
                baseline_run_id=baseline_run_id,
                gates=tuple(gates),
                gates_passed=ok,
                status="pending_approval" if ok else "rejected_by_gates",
                created_at=datetime.now(UTC),
                notes=notes,
                regression_cases=regression_cases,
            )
        )

    @staticmethod
    def _check_role(role: str, approver_roles: tuple[str, ...]) -> None:
        if role not in approver_roles:
            raise ConfigError(
                f"role {role!r} cannot approve releases. Approver roles: {list(approver_roles)}"
            )

    def approve(
        self,
        decision_id: str,
        approver: str,
        role: str,
        comment: str,
        approver_roles: tuple[str, ...],
    ) -> ReleaseDecision:
        self._check_role(role, approver_roles)
        d = self.decision(decision_id)
        if d.status != "pending_approval":
            raise ConfigError(
                f"decision {decision_id} has status {d.status}. Only a decision "
                "that waits for approval can get an approval."
            )
        now = datetime.now(UTC)
        approved = d.model_copy(
            update={
                "status": "approved",
                "approval": ApprovalRecord(
                    approver=approver, role=role, decision="approve", comment=comment, at=now
                ),
            }
        )
        self._save(approved)
        pointer = self._pointer()
        pointer["stack"].append(d.release.release_id)
        _write(self.root / "production.json", json.dumps(pointer, indent=2))
        if d.regression_cases:
            self.add_regression_cases(list(d.regression_cases))
        self._log(
            HistoryEvent(
                action="approve",
                release_id=d.release.release_id,
                version=d.release.version,
                actor=approver,
                role=role,
                at=now,
                detail=comment,
            )
        )
        return approved

    def reject(
        self,
        decision_id: str,
        approver: str,
        role: str,
        comment: str,
        approver_roles: tuple[str, ...],
    ) -> ReleaseDecision:
        self._check_role(role, approver_roles)
        d = self.decision(decision_id)
        if d.status != "pending_approval":
            raise ConfigError(f"decision {decision_id} has status {d.status}")
        now = datetime.now(UTC)
        rejected = d.model_copy(
            update={
                "status": "rejected",
                "approval": ApprovalRecord(
                    approver=approver, role=role, decision="reject", comment=comment, at=now
                ),
            }
        )
        self._log(
            HistoryEvent(
                action="reject",
                release_id=d.release.release_id,
                version=d.release.version,
                actor=approver,
                role=role,
                at=now,
                detail=comment,
            )
        )
        return self._save(rejected)

    def rollback(
        self, approver: str, role: str, reason: str, approver_roles: tuple[str, ...]
    ) -> Release:
        self._check_role(role, approver_roles)
        pointer = self._pointer()
        if len(pointer["stack"]) < 2:
            raise ConfigError("there is no previous release to roll back to")
        pointer["stack"].pop()
        _write(self.root / "production.json", json.dumps(pointer, indent=2))
        current = self._release(pointer["stack"][-1])
        self._log(
            HistoryEvent(
                action="rollback",
                release_id=current.release_id,
                version=current.version,
                actor=approver,
                role=role,
                at=datetime.now(UTC),
                detail=reason,
            )
        )
        return current

    # ------------------------------------------------------------------ regression suite
    def regression_cases(self) -> list[str]:
        p = self.root / "regression_cases.json"
        return json.loads(p.read_text()) if p.exists() else []

    def add_regression_cases(self, case_ids: list[str]) -> list[str]:
        merged = sorted(set(self.regression_cases()) | set(case_ids))
        _write(self.root / "regression_cases.json", json.dumps(merged, indent=2))
        return merged
