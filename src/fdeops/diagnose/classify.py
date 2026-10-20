"""Deterministic failure classification.

Each rule looks for one symptom in the scores and the episode, and records evidence for it. The
causal order then selects the primary class. The classifier never reads model output to make a
judgment, thus the same trial always gets the same label.
"""

from collections.abc import Callable, Mapping

from fdeops.agent.episode import EpisodeResult
from fdeops.core.errors import InvariantError
from fdeops.diagnose.taxonomy import (
    CAUSAL_ORDER,
    DESCRIPTIONS,
    Evidence,
    FailureClass,
    FailureLabel,
)
from fdeops.eval.runner import RunResult, TrialResult
from fdeops.eval.types import Score

INFRA_ERRORS = frozenset(
    {"TIMEOUT", "UNAVAILABLE", "RATE_LIMITED", "MALFORMED_RESPONSE", "UNAUTHENTICATED"}
)
AUTHZ_RULE_PARTS = ("wrong_customer", "unauthorized_role")


def _failed(score: Score | None) -> bool:
    return score is not None and score.passed is False


def _tool_spans(ep: EpisodeResult, codes: frozenset[str] | None = None) -> list[Evidence]:
    out = []
    for t in ep.tool_calls:
        if t.ok or (codes is not None and t.error_code not in codes):
            continue
        out.append(
            Evidence(
                kind="span",
                ref=t.span_id,
                detail=f"{t.op} failed with {t.error_code} after {t.attempts} attempt(s)",
            )
        )
    return out


Rule = Callable[[TrialResult, "Knowledge"], list[Evidence]]
Knowledge = Mapping[str, tuple[str, ...]]


def _injection(tr: TrialResult, knowledge: Knowledge) -> list[Evidence]:
    s = tr.score("injection")
    if not _failed(s):
        return []
    if s is None:
        raise InvariantError("s must be set here")
    return [
        Evidence(
            kind="score", ref="injection", detail=f"executed {s.details.get('executed_forbidden')}"
        )
    ]


def _stale(tr: TrialResult, knowledge: Knowledge) -> list[Evidence]:
    ep = tr.episode
    stale_chunks = [c for c in ep.retrieved if c.stale]
    if not stale_chunks:
        return []
    facts = tr.score("facts")
    stale_said = bool(facts and facts.details.get("forbidden_present"))
    # Stale context alone is a correlation. Require a link: the reply said a stale fact, or a
    # violation occurred of a rule that a stale section controls.
    governed = {r for c in stale_chunks for r in knowledge.get(c.section_key, ())}
    linked = [v for v in ep.violations if v.rule in governed]
    if not (stale_said or linked):
        return []
    # Show the stale sections that explain the failure: the ones that control a violated rule.
    # If the link is a stale fact, show all stale sections.
    violated = {v.rule for v in linked}
    causal = {c.uid for c in stale_chunks if set(knowledge.get(c.section_key, ())) & violated}
    ev = [
        Evidence(kind="stale_chunk", ref=uid, detail="superseded section given to the agent")
        for uid in sorted(causal or {c.uid for c in stale_chunks})
    ]
    if stale_said and facts is not None:
        ev.append(
            Evidence(
                kind="fact",
                ref="facts",
                detail=f"stale facts in reply: {facts.details['forbidden_present']}",
            )
        )
    ev += [Evidence(kind="violation", ref=v.rule, detail=v.message) for v in linked]
    return ev


def _permission(tr: TrialResult, knowledge: Knowledge) -> list[Evidence]:
    ep = tr.episode
    ev = _tool_spans(ep, frozenset({"PERMISSION_DENIED"}))
    ev += [
        Evidence(kind="violation", ref=v.rule, detail=v.message)
        for v in (*ep.violations, *ep.blocked)
        if any(p in v.rule for p in AUTHZ_RULE_PARTS)
    ]
    return ev


def _budget(tr: TrialResult, knowledge: Knowledge) -> list[Evidence]:
    ep = tr.episode
    if ep.outcome not in ("budget_exhausted", "model_error"):
        return []
    return [
        Evidence(
            kind="score",
            ref="episode",
            detail=f"episode ended with {ep.outcome} after "
            f"{ep.steps} steps. {ep.error or ''}".strip(),
        )
    ]


def _unhandled(tr: TrialResult, knowledge: Knowledge) -> list[Evidence]:
    if not _failed(tr.score("outcome")):
        return []
    return _tool_spans(tr.episode, INFRA_ERRORS)


def _escalation(cell: str) -> Rule:
    def rule(tr: TrialResult, knowledge: Knowledge) -> list[Evidence]:
        s = tr.score("escalation")
        if s is None or s.details.get("cell") != cell:
            return []
        return [
            Evidence(
                kind="score",
                ref="escalation",
                detail=f"{cell}: necessary code {s.details.get('expected_reason')}, "
                f"agent code {s.details.get('reason')}",
            )
        ]

    return rule


def _bad_arguments(tr: TrialResult, knowledge: Knowledge) -> list[Evidence]:
    ev: list[Evidence] = []
    out = tr.score("outcome")
    if out is not None and out.details.get("missing") and out.details.get("unexpected"):
        missing = {m["collection"] for m in out.details["missing"]}
        wrong = [u for u in out.details["unexpected"] if u.split(" ")[1].split("/")[0] in missing]
        ev += [
            Evidence(kind="change", ref=u, detail="a change with incorrect values") for u in wrong
        ]
    ev += _tool_spans(tr.episode, frozenset({"INVALID_ARGUMENT", "CONFLICT"}))
    ev += [
        Evidence(kind="violation", ref=v.rule, detail=v.message)
        for v in tr.episode.violations
        if v.rule.endswith("amount_mismatch")
    ]
    return ev if (ev and _failed(out)) else []


def _policy(tr: TrialResult, knowledge: Knowledge) -> list[Evidence]:
    return [
        Evidence(kind="violation", ref=v.rule, detail=v.message)
        for v in tr.episode.violations
        if v.severity in ("critical", "major")
    ]


def _clarification(tr: TrialResult, knowledge: Knowledge) -> list[Evidence]:
    s = tr.score("clarification")
    return (
        [Evidence(kind="score", ref="clarification", detail="acted before it asked")]
        if _failed(s)
        else []
    )


def _wrong_tool(tr: TrialResult, knowledge: Knowledge) -> list[Evidence]:
    s = tr.score("tool_use")
    if not _failed(s):
        return []
    if s is None:
        raise InvariantError("s must be set here")
    return [
        Evidence(
            kind="score",
            ref="tool_use",
            detail=f"missing {s.details.get('missing_required')}, forbidden "
            f"{s.details.get('forbidden_attempted')}",
        )
    ]


def _retrieval_miss(tr: TrialResult, knowledge: Knowledge) -> list[Evidence]:
    s = tr.score("retrieval.recall")
    if s is None or s.passed is not False:
        return []
    if not (_failed(tr.score("facts")) or _failed(tr.score("outcome"))):
        return []
    return [
        Evidence(
            kind="score",
            ref="retrieval.recall",
            detail=f"gold sections not retrieved: {s.details.get('missing')}",
        )
    ]


def _grounding(tr: TrialResult, knowledge: Knowledge) -> list[Evidence]:
    ev = []
    facts = tr.score("facts")
    if _failed(facts) and facts is not None and facts.details.get("missing"):
        ev.append(
            Evidence(
                kind="fact",
                ref="facts",
                detail=f"necessary facts missing: {facts.details['missing']}",
            )
        )
    judge = tr.score("judge.groundedness")
    if _failed(judge) and judge is not None:
        ev.append(
            Evidence(
                kind="score",
                ref="judge.groundedness",
                detail=str(judge.details.get("rationale", "")),
            )
        )
    return ev


def _residual(tr: TrialResult, knowledge: Knowledge) -> list[Evidence]:
    out = tr.score("outcome")
    detail = str(out.details) if out is not None else "no outcome score"
    return [Evidence(kind="score", ref="outcome", detail=detail[:300])]


RULES: dict[FailureClass, Rule] = {
    FailureClass.INJECTION_FOLLOWED: _injection,
    FailureClass.STALE_KNOWLEDGE: _stale,
    FailureClass.PERMISSION_VIOLATION: _permission,
    FailureClass.TIMEOUT_OR_BUDGET: _budget,
    FailureClass.UNHANDLED_TOOL_ERROR: _unhandled,
    FailureClass.MISSED_ESCALATION: _escalation("fn"),
    FailureClass.OVER_ESCALATION: _escalation("fp"),
    FailureClass.BAD_ARGUMENTS: _bad_arguments,
    FailureClass.POLICY_VIOLATION: _policy,
    FailureClass.CLARIFICATION_FAILURE: _clarification,
    FailureClass.WRONG_TOOL: _wrong_tool,
    FailureClass.RETRIEVAL_MISS: _retrieval_miss,
    FailureClass.GROUNDING_FAILURE: _grounding,
    FailureClass.REASONING_ERROR: _residual,
}


def classify(tr: TrialResult, knowledge: Knowledge | None = None) -> FailureLabel | None:
    """``knowledge`` maps KB section keys to the policy rules they control.

    Use ``pack.knowledge_rules``.
    """
    if tr.success:
        return None
    found: dict[FailureClass, list[Evidence]] = {}
    for cls in CAUSAL_ORDER[:-1]:
        ev = RULES[cls](tr, knowledge or {})
        if ev:
            found[cls] = ev
    if not found:
        found[FailureClass.REASONING_ERROR] = _residual(tr, {})
    ordered = [c for c in CAUSAL_ORDER if c in found]
    primary = ordered[0]
    evidence = tuple(e for c in ordered for e in found[c])
    return FailureLabel(
        case_id=tr.case_id,
        trial=tr.trial,
        scenario=tr.scenario,
        tags=tr.tags,
        primary=primary,
        secondary=tuple(ordered[1:]),
        evidence=evidence,
        summary=DESCRIPTIONS[primary],
    )


def classify_run(run: RunResult, knowledge: Knowledge | None = None) -> list[FailureLabel]:
    return [lbl for tr in run.results if (lbl := classify(tr, knowledge)) is not None]
