from fdeops.agent.config import AgentConfig, ModelRef
from fdeops.agent.episode import run_episode
from fdeops.eval.calibration import calibrate
from fdeops.eval.judges import COMMUNICATION, GROUNDEDNESS, LLMJudge
from fdeops.eval.types import EvalContext
from fdeops.llm.scripted import ScriptedLLM
from fdeops.llm.types import LLMRequest
from fdeops.retrieval.retriever import RetrievalConfig
from fdeops.tenancy.loader import Tenant
from fdeops.world.cases import Case

from ..agent.conftest import first

CFG = AgentConfig(
    id="h",
    model=ModelRef(provider="heuristic", name="h"),
    retrieval=RetrievalConfig(include_superseded=False),
)


def episode(tenant: Tenant, cases: list[Case]):  # type: ignore[no-untyped-def]
    case = first(cases, "refund_eligible")
    return case, run_episode(case, tenant, CFG, tenant.pack.heuristic_model(0, {}), trial=0)


def test_judge_parses_fenced_json(tenant: Tenant, cases: list[Case]) -> None:
    seen: list[LLMRequest] = []

    def respond(r: LLMRequest) -> str:
        seen.append(r)
        return '```json\n{"score": 5, "rationale": "every claim is supported"}\n```'

    case, ep = episode(tenant, cases)
    judge = LLMJudge(ScriptedLLM(respond), GROUNDEDNESS, model="judge-model")
    score = judge.evaluate(case, ep, EvalContext(tenant))[0]
    assert score.name == "judge.groundedness"
    assert score.value == 5 and score.passed is True
    prompt = seen[0].messages[-1].content
    assert ep.final_message in prompt
    assert "refund-policy" in prompt  # evidence shown to the judge
    assert seen[0].temperature == 0.0


def test_judge_threshold(tenant: Tenant, cases: list[Case]) -> None:
    case, ep = episode(tenant, cases)
    judge = LLMJudge(
        ScriptedLLM(lambda r: '{"score": 2, "rationale": "vague"}'), COMMUNICATION, model="m"
    )
    s = judge.evaluate(case, ep, EvalContext(tenant))[0]
    assert s.value == 2 and s.passed is False


def test_judge_parse_failure_is_not_pass(tenant: Tenant, cases: list[Case]) -> None:
    case, ep = episode(tenant, cases)
    for bad in ["I think it's fine", '{"score": 9}', '{"score": "high"}']:
        s = LLMJudge(ScriptedLLM(lambda r, b=bad: b), GROUNDEDNESS, model="m").evaluate(
            case, ep, EvalContext(tenant)
        )[0]
        assert s.passed is None and "error" in s.details


def test_judge_model_failure_is_not_pass(tenant: Tenant, cases: list[Case]) -> None:
    from fdeops.llm.openai_compat import LLMUnavailable

    def boom(r: LLMRequest) -> str:
        raise LLMUnavailable("down", retryable=True)

    case, ep = episode(tenant, cases)
    s = LLMJudge(ScriptedLLM(boom), GROUNDEDNESS, model="m").evaluate(case, ep, EvalContext(tenant))
    assert s[0].passed is None and "down" in s[0].details["error"]


def test_judge_skips_episode_without_reply(tenant: Tenant, cases: list[Case]) -> None:
    case = first(cases, "refund_over_limit")
    ep = run_episode(case, tenant, CFG, tenant.pack.heuristic_model(0, {}), trial=0)
    assert ep.agent_messages == ()
    judge = LLMJudge(ScriptedLLM(lambda r: '{"score": 5, "rationale": ""}'), GROUNDEDNESS, "m")
    assert judge.evaluate(case, ep, EvalContext(tenant)) == []


def test_calibration_kappa_and_floor() -> None:
    keys = [f"k{i}" for i in range(50)]
    human = dict(zip(keys, [True] * 25 + [False] * 25, strict=True))
    judge = dict(zip(keys, [True] * 20 + [False] * 5 + [True] * 10 + [False] * 15, strict=True))
    # flip so the table matches the textbook kappa = 0.4 example
    rep = calibrate("judge.groundedness", judge, human, floor=0.6)
    assert rep.n == 50
    assert round(rep.kappa, 3) == 0.4
    assert rep.agreement == 0.7
    assert rep.confusion == {
        "judge_pass": {"human_pass": 20, "human_fail": 10},
        "judge_fail": {"human_pass": 5, "human_fail": 15},
    }
    assert rep.meets_floor is False
    assert calibrate("j", human, human).meets_floor


def test_calibration_only_joins_shared_keys() -> None:
    rep = calibrate("j", {"a": True, "b": False, "c": True}, {"a": True, "b": False})
    assert rep.n == 2


def test_failed_judgment_survives_run_roundtrip(
    tenant: Tenant, cases: list[Case], tmp_path
) -> None:  # type: ignore[no-untyped-def]
    from fdeops.eval.evaluators import DEFAULT_EVALUATORS
    from fdeops.eval.report import load_run, save_run, summarize
    from fdeops.eval.runner import run_eval

    ds = tenant.build_datasets("support-core")["test"]
    picked = tuple(c for c in ds.cases if c.scenario == "refund_eligible")[:2]
    one = ds.model_copy(update={"cases": picked})
    broken = LLMJudge(ScriptedLLM(lambda r: "not json"), GROUNDEDNESS, model="m")
    run = run_eval(
        tenant,
        CFG,
        one,
        tenant.pack.heuristic_model(0, {}),
        evaluators=(*DEFAULT_EVALUATORS, broken),
    )
    judged = [s for r in run.results for s in r.scores if s.name == "judge.groundedness"]
    assert len(judged) == 2 and all(s.passed is None for s in judged)
    assert load_run(save_run(run, tmp_path)) == run
    assert "judge.groundedness" not in summarize(run).evaluator_pass_rates
