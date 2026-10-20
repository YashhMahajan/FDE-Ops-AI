"""Signals for each trial that a production deployment can see without an oracle."""

from fdeops.agent.support_agent import TurnOutcome
from fdeops.core.model import FrozenModel
from fdeops.eval.runner import RunResult, TrialResult

RATE_SIGNALS: dict[str, str] = {
    "escalation": "The agent sent the ticket to a person.",
    "clarification": "The agent asked the customer for more data.",
    "tool_error": "One or more tool calls failed after all retries.",
    "episode_error": "The episode stopped with a model error or at its step budget.",
    "policy_flag": "The runtime policy monitor flagged one or more operations.",
    "critical_flag": "The runtime policy monitor flagged a critical operation.",
    "guardrail_block": "A guardrail in enforce mode blocked an operation.",
    "stale_context": "The context had a superseded version of a knowledge section.",
    "data_issue": "The ingest step found a problem in the business data.",
}

VALUE_SIGNALS: dict[str, str] = {
    "latency_ms": "Model latency and tool latency for each ticket.",
    "tokens": "Input tokens and output tokens for each ticket.",
    "steps": "Agent steps for each ticket.",
}


class TrialSignals(FrozenModel):
    case_id: str
    trial: int
    scenario: str
    flags: dict[str, bool]
    values: dict[str, float]
    failed: bool
    """The oracle result. The monitor does not use it. Only the detection-quality check uses it."""


def trial_signals(t: TrialResult) -> TrialSignals:
    e = t.episode
    flagged = (*e.violations, *e.blocked)
    flags = {
        "escalation": e.outcome == TurnOutcome.ESCALATE,
        "clarification": e.outcome == TurnOutcome.CLARIFY,
        "tool_error": any(not c.ok for c in e.tool_calls),
        "episode_error": e.outcome in (TurnOutcome.MODEL_ERROR, TurnOutcome.BUDGET_EXHAUSTED)
        or e.error is not None,
        "policy_flag": bool(flagged),
        "critical_flag": any(v.severity == "critical" for v in flagged),
        "guardrail_block": bool(e.blocked),
        "stale_context": any(c.stale for c in e.retrieved),
        "data_issue": bool(e.data_issues),
    }
    values = {
        "latency_ms": e.llm_latency_ms + e.tool_latency_ms,
        "tokens": float(e.usage.input_tokens + e.usage.output_tokens),
        "steps": float(e.steps),
    }
    return TrialSignals(
        case_id=t.case_id,
        trial=t.trial,
        scenario=t.scenario,
        flags=flags,
        values=values,
        failed=not t.success,
    )


def run_signals(run: RunResult) -> list[TrialSignals]:
    """The signals in ticket order. The order of the run is the order of the traffic."""
    return [trial_signals(t) for t in run.results]
