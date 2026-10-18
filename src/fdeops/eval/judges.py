"""LLM-as-judge for qualities deterministic checks can't measure (groundedness, communication).

Judges never gate a release on their own authority: their agreement with human labels is measured
first (see ``calibration``). An unparseable or failed judgment is recorded as "no verdict"
(``passed=None``), never silently as a pass.
"""

import json
import re

from fdeops.agent.episode import EpisodeResult
from fdeops.core.errors import FdeOpsError
from fdeops.core.model import FrozenModel
from fdeops.eval.types import EvalContext, Score
from fdeops.llm.types import LLMClient, LLMRequest, Message
from fdeops.world.cases import Case


class JudgeRubric(FrozenModel):
    name: str
    instructions: str
    scale_min: int = 1
    scale_max: int = 5
    pass_threshold: int = 4


GROUNDEDNESS = JudgeRubric(
    name="groundedness",
    instructions=(
        "Judge whether every factual claim in the AGENT REPLY about policy, amounts, dates or "
        "timelines is supported by the EVIDENCE (knowledge base excerpts and tool results). "
        "5 = every claim supported; 3 = minor unsupported detail; 1 = a material claim is "
        "unsupported or contradicted. Ignore tone."
    ),
)
COMMUNICATION = JudgeRubric(
    name="communication",
    instructions=(
        "Judge the AGENT REPLY as a support message: does it clearly state the outcome, explain "
        "the reason, and tell the customer what happens next, politely and concisely? "
        "5 = excellent; 3 = acceptable but unclear or incomplete; 1 = confusing or rude."
    ),
)

_SYSTEM = (
    "You are a strict evaluator of customer-support replies. Respond with only a JSON "
    'object: {"score": <integer>, "rationale": "<one sentence>"}.'
)


def _evidence(ep: EpisodeResult) -> str:
    chunks = {c.uid: f"[{c.uid}] {c.text}" for c in ep.retrieved}
    tools = [m.content for m in ep.transcript if m.role == "tool"]
    return "\n\n".join([*chunks.values(), *(f"TOOL RESULT: {t}" for t in tools)])


def _parse(text: str, rubric: JudgeRubric) -> tuple[int, str]:
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError("no JSON object in judge output")
    data = json.loads(match.group(0))
    score = data.get("score")
    if not isinstance(score, int) or not rubric.scale_min <= score <= rubric.scale_max:
        raise ValueError(f"score {score!r} outside {rubric.scale_min}..{rubric.scale_max}")
    return score, str(data.get("rationale", ""))


class LLMJudge:
    def __init__(self, llm: LLMClient, rubric: JudgeRubric, model: str) -> None:
        self.llm = llm
        self.rubric = rubric
        self.model = model
        self.name = f"judge.{rubric.name}"

    def evaluate(self, case: Case, ep: EpisodeResult, ctx: EvalContext) -> list[Score]:
        reply = "\n\n".join(ep.agent_messages)
        if not reply:
            return []
        prompt = (
            f"{self.rubric.instructions}\n\nCUSTOMER TICKET:\n{case.ticket.body}\n\n"
            f"EVIDENCE:\n{_evidence(ep)}\n\nAGENT REPLY:\n{reply}"
        )
        request = LLMRequest(
            model=self.model,
            temperature=0.0,
            max_tokens=300,
            seed=0,
            messages=(
                Message(role="system", content=_SYSTEM),
                Message(role="user", content=prompt),
            ),
        )
        try:
            score, rationale = _parse(self.llm.complete(request).content, self.rubric)
        except (FdeOpsError, ValueError, json.JSONDecodeError) as e:
            return [
                Score(
                    evaluator=self.name,
                    name=self.name,
                    value=None,
                    passed=None,
                    details={"error": f"{type(e).__name__}: {e}"},
                )
            ]
        return [
            Score(
                evaluator=self.name,
                name=self.name,
                value=float(score),
                passed=score >= self.rubric.pass_threshold,
                details={"rationale": rationale},
            )
        ]
