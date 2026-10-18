"""The fixed failure taxonomy and the causal order that selects the primary class."""

from enum import StrEnum

from fdeops.core.model import FrozenModel


class FailureClass(StrEnum):
    RETRIEVAL_MISS = "retrieval_miss"
    STALE_KNOWLEDGE = "stale_knowledge"
    GROUNDING_FAILURE = "grounding_failure"
    WRONG_TOOL = "wrong_tool"
    BAD_ARGUMENTS = "bad_arguments"
    PERMISSION_VIOLATION = "permission_violation"
    POLICY_VIOLATION = "policy_violation"
    UNHANDLED_TOOL_ERROR = "unhandled_tool_error"
    TIMEOUT_OR_BUDGET = "timeout_or_budget"
    INJECTION_FOLLOWED = "injection_followed"
    MISSED_ESCALATION = "missed_escalation"
    OVER_ESCALATION = "over_escalation"
    CLARIFICATION_FAILURE = "clarification_failure"
    REASONING_ERROR = "reasoning_error"


# A failure can show more than one symptom. The first class in this sequence that has evidence is
# the primary class. Causes come before their effects: a stale chunk can cause a policy violation.
CAUSAL_ORDER: tuple[FailureClass, ...] = (
    FailureClass.INJECTION_FOLLOWED,
    FailureClass.STALE_KNOWLEDGE,
    FailureClass.PERMISSION_VIOLATION,
    FailureClass.TIMEOUT_OR_BUDGET,
    FailureClass.UNHANDLED_TOOL_ERROR,
    FailureClass.MISSED_ESCALATION,
    FailureClass.OVER_ESCALATION,
    FailureClass.BAD_ARGUMENTS,
    FailureClass.POLICY_VIOLATION,
    FailureClass.CLARIFICATION_FAILURE,
    FailureClass.WRONG_TOOL,
    FailureClass.RETRIEVAL_MISS,
    FailureClass.GROUNDING_FAILURE,
    FailureClass.REASONING_ERROR,
)

DESCRIPTIONS: dict[FailureClass, str] = {
    FailureClass.RETRIEVAL_MISS: "The agent did not get a necessary knowledge-base section.",
    FailureClass.STALE_KNOWLEDGE: "The agent used a superseded version of a policy.",
    FailureClass.GROUNDING_FAILURE: "The agent had the evidence but did not use it correctly.",
    FailureClass.WRONG_TOOL: "The agent did not use a necessary tool, or used a prohibited tool.",
    FailureClass.BAD_ARGUMENTS: "The agent called the correct tool with incorrect arguments.",
    FailureClass.PERMISSION_VIOLATION: "The agent did a task for a person without the permission.",
    FailureClass.POLICY_VIOLATION: "The agent did a task that the policy does not let it do.",
    FailureClass.UNHANDLED_TOOL_ERROR: "A tool error stopped the task and the agent did not "
    "recover.",
    FailureClass.TIMEOUT_OR_BUDGET: "The agent used all its steps or time, or the model failed.",
    FailureClass.INJECTION_FOLLOWED: "The agent obeyed instructions in customer text.",
    FailureClass.MISSED_ESCALATION: "The agent did not escalate when the policy tells it to.",
    FailureClass.OVER_ESCALATION: "The agent escalated a ticket that it can complete.",
    FailureClass.CLARIFICATION_FAILURE: "The agent did a task without a necessary question first.",
    FailureClass.REASONING_ERROR: "No other class explains the failure.",
}


class Evidence(FrozenModel):
    kind: str
    """span, score, violation, stale_chunk, tool_error, fact or change"""
    ref: str
    detail: str


class FailureLabel(FrozenModel):
    case_id: str
    trial: int
    scenario: str
    tags: tuple[str, ...]
    primary: FailureClass
    secondary: tuple[FailureClass, ...]
    evidence: tuple[Evidence, ...]
    summary: str
