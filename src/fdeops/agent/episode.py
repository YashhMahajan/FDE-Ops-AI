"""One episode: a case, a fresh copy of the tenant's world, the agent, and a deterministic customer.

The connector stack the agent calls through, outermost first:
permission guard → policy monitor → resilience (timeouts, retries, idempotency) → fault injection
→ the domain APIs.
"""

import json
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from fdeops.agent.config import AgentConfig
from fdeops.agent.prompts import load_prompt
from fdeops.agent.support_agent import (
    SupportAgent,
    ToolCallRecord,
    TurnOutcome,
    TurnResult,
    format_chunks,
)
from fdeops.connectors.audit import AuditLog
from fdeops.connectors.base import Connector, ConnectorRegistry, OpContext
from fdeops.connectors.faults import FaultInjectingConnector, FaultRule
from fdeops.connectors.guard import PermissionGuard
from fdeops.connectors.policy_monitor import PolicyMonitor
from fdeops.connectors.resilience import CircuitBreaker, ResilientConnector
from fdeops.core.clock import FakeClock
from fdeops.core.hashing import sha256_hex
from fdeops.core.ids import stable_id
from fdeops.core.model import FrozenModel
from fdeops.llm.types import LLMClient, Message, ToolCall, Usage
from fdeops.retrieval.retriever import RetrievedChunk, Retriever
from fdeops.tenancy.loader import Tenant
from fdeops.trace.spans import SpanKind, Trace, Tracer
from fdeops.world.cases import Case
from fdeops.world.ingest import RecordIssue, insert_records
from fdeops.world.policy import Violation
from fdeops.world.state import StateChange, diff_states


class EpisodeResult(FrozenModel):
    case_id: str
    trial: int
    outcome: TurnOutcome
    turns: int
    steps: int
    changes: tuple[StateChange, ...]
    transcript: tuple[Message, ...]
    tool_calls: tuple[ToolCallRecord, ...]
    retrieved: tuple[RetrievedChunk, ...]
    violations: tuple[Violation, ...]
    blocked: tuple[Violation, ...]
    faults_injected: tuple[tuple[str, str], ...]
    agent_messages: tuple[str, ...]
    final_message: str
    clarified_before_action: bool
    usage: Usage
    llm_latency_ms: float
    tool_latency_ms: float
    audit_ok: bool
    trace: Trace
    error: str | None = None
    data_issues: tuple[RecordIssue, ...] = ()
    """Problems that the ingest step found in the case data (for example, a missing email)."""


def episode_seed(case_id: str, trial: int) -> int:
    return int(sha256_hex(f"{case_id}:{trial}")[:12], 16)


def _gold_chunks(case: Case, tenant: Tenant) -> list[RetrievedChunk]:
    out: list[RetrievedChunk] = []
    for key in case.expected.gold_sections:
        s = tenant.kb.effective(key, case.now.date())
        if s is not None:
            out.append(
                RetrievedChunk(
                    section_key=s.key,
                    version=s.version,
                    uid=s.uid,
                    title=s.title,
                    text=s.text,
                    score=1.0,
                    rank=len(out) + 1,
                    stale=False,
                )
            )
    return out


def _ticket_message(case: Case, chunks: list[RetrievedChunk] | None) -> str:
    t = case.ticket
    text = f"New ticket {t.ticket_id}\nFrom: {t.requester_email}\nSubject: {t.subject}\n\n{t.body}"
    if chunks is not None:
        text += "\n\n---\nKnowledge base excerpts retrieved for this ticket:\n\n" + format_chunks(
            chunks
        )
    return text


@dataclass
class _Env:
    """Everything one episode needs: a private world copy and the full connector stack."""

    case: Case
    tenant: Tenant
    config: AgentConfig
    trial: int
    clock: FakeClock
    seed: int
    state: Any
    before: Any
    audit: AuditLog
    monitors: list[PolicyMonitor]
    faulty: list[FaultInjectingConnector]
    registry: ConnectorRegistry
    tracer: Tracer
    retriever: Retriever
    ctx: OpContext
    data_issues: list[RecordIssue]


def _build_env(
    case: Case,
    tenant: Tenant,
    config: AgentConfig,
    trial: int,
    faults: Sequence[FaultRule],
    retriever: Retriever | None,
) -> _Env:
    pack = tenant.pack
    clock = FakeClock(case.now)
    seed = episode_seed(case.id, trial)
    rng = random.Random(seed)
    state: Any = tenant.base_world.copy()
    data_issues, *_ = insert_records(state, case.fixtures, pack.references, pack.normalizers)
    pack.open_ticket(state, case.ticket, case.now)
    before = state.copy()
    audit = AuditLog()
    checker = pack.policy_engine(tenant.policy)
    faulty: list[FaultInjectingConnector] = []
    monitors: list[PolicyMonitor] = []
    stack: list[Connector] = []
    for base in pack.build_connectors(state):
        inner: Connector = base
        if faults:
            injector = FaultInjectingConnector(inner, list(faults), rng)
            faulty.append(injector)
            inner = injector
        inner = ResilientConnector(
            inner,
            retry=config.retry,
            breaker=CircuitBreaker(clock=clock),
            limiter=None,
            timeout_s=config.tool_timeout_s,
            clock=clock,
            rng=rng,
        )
        monitor = PolicyMonitor(
            inner, checker, state, case.ticket.requester_email, mode=config.policy_guardrail
        )
        monitors.append(monitor)
        stack.append(PermissionGuard(monitor, audit))
    return _Env(
        case=case,
        tenant=tenant,
        config=config,
        trial=trial,
        clock=clock,
        seed=seed,
        state=state,
        before=before,
        audit=audit,
        monitors=monitors,
        faulty=faulty,
        registry=ConnectorRegistry(stack),
        tracer=Tracer(stable_id("trc", case.id, trial, config.content_hash), clock),
        retriever=retriever or Retriever(tenant.kb, config.retrieval),
        ctx=OpContext(
            tenant_id=tenant.id, actor="agent", scopes=tenant.scopes, clock=clock, case_id=case.id
        ),
        data_issues=list(data_issues),
    )


def _initial_context(env: _Env, agent: SupportAgent) -> list[RetrievedChunk] | None:
    if env.config.oracle_context:
        return _gold_chunks(env.case, env.tenant)
    if env.config.auto_context:
        t = env.case.ticket
        return agent.retrieve(f"{t.subject}\n{t.body}", env.case.now)
    return None


def _customer_answer(env: _Env, tool_calls: Sequence[ToolCallRecord]) -> str | None:
    question = next(
        (c.args or {} for c in reversed(tool_calls) if c.op == "ask_clarifying_question" and c.ok),
        {},
    )
    answer = env.tenant.pack.user_simulator().respond(env.case, str(question.get("question", "")))
    if answer is not None:
        env.clock.advance(60)
        env.tenant.pack.add_customer_reply(
            env.state, env.case.ticket.ticket_id, answer, env.clock.now()
        )
    return answer


def _finish(
    env: _Env,
    *,
    outcome: TurnOutcome,
    turns: int,
    steps: int,
    messages: Sequence[Message],
    tool_calls: Sequence[ToolCallRecord],
    retrieved: Sequence[RetrievedChunk],
    usage: Usage,
    llm_ms: float,
    error: str | None,
) -> EpisodeResult:
    first_clarify = next(
        (i for i, c in enumerate(tool_calls) if c.op == "ask_clarifying_question" and c.ok), None
    )
    first_action = next(
        (i for i, c in enumerate(tool_calls) if c.ok and c.mutating and c.terminal is None), None
    )
    agent_msgs = tuple(env.tenant.pack.agent_messages(env.state, env.case.ticket.ticket_id))
    return EpisodeResult(
        case_id=env.case.id,
        trial=env.trial,
        outcome=outcome,
        turns=turns,
        steps=steps,
        changes=tuple(diff_states(env.before, env.state)),
        transcript=tuple(messages),
        tool_calls=tuple(tool_calls),
        retrieved=tuple(retrieved),
        violations=tuple(v for m in env.monitors for v in m.violations),
        blocked=tuple(v for m in env.monitors for v in m.blocked),
        faults_injected=tuple(f for c in env.faulty for f in c.injected),
        agent_messages=agent_msgs,
        final_message=agent_msgs[-1] if agent_msgs else "",
        clarified_before_action=first_clarify is not None
        and (first_action is None or first_clarify < first_action),
        usage=usage,
        llm_latency_ms=llm_ms,
        tool_latency_ms=sum(c.latency_ms for c in tool_calls),
        audit_ok=env.audit.verify() is None,
        data_issues=tuple(env.data_issues),
        trace=env.tracer.trace(),
        error=error,
    )


def run_episode(
    case: Case,
    tenant: Tenant,
    config: AgentConfig,
    llm: LLMClient,
    trial: int,
    faults: Sequence[FaultRule] = (),
    retriever: Retriever | None = None,
) -> EpisodeResult:
    """Run the reference support agent on one case."""
    env = _build_env(case, tenant, config, trial, faults, retriever)
    agent = SupportAgent(config, llm, env.registry, env.retriever, env.tracer)
    prompt = load_prompt(config.prompt_version)
    reasons = ", ".join(getattr(tenant.policy, "escalation_reasons", ()))
    tool_calls: list[ToolCallRecord] = []
    retrieved: list[RetrievedChunk] = []
    usage = Usage()
    llm_ms = 0.0
    steps = turns = 0
    outcome = TurnOutcome.BUDGET_EXHAUSTED
    error: str | None = None
    with env.tracer.span(
        SpanKind.AGENT,
        "episode",
        **{
            "fdeops.case_id": case.id,
            "fdeops.trial": trial,
            "fdeops.agent_config": config.content_hash,
            "fdeops.prompt": prompt.hash,
        },
    ):
        auto = _initial_context(env, agent)
        retrieved.extend(auto or [])
        messages = [
            Message(
                role="system",
                content=prompt.render(
                    company=tenant.company,
                    ticket_id=case.ticket.ticket_id,
                    today=case.now.date().isoformat(),
                    reason_codes=reasons,
                ),
            ),
            Message(role="user", content=_ticket_message(case, auto)),
        ]
        for turn in range(1, config.max_turns + 1):
            turns = turn
            r = agent.run_turn(messages, env.ctx, env.clock.now(), turn, env.seed + turn)
            tool_calls += r.tool_calls
            retrieved += r.retrieved
            steps += r.steps
            llm_ms += r.llm_latency_ms
            usage = Usage(
                input_tokens=usage.input_tokens + r.usage.input_tokens,
                output_tokens=usage.output_tokens + r.usage.output_tokens,
            )
            outcome, error = r.outcome, r.error or error
            if outcome != TurnOutcome.CLARIFY:
                break
            answer = _customer_answer(env, r.tool_calls)
            if answer is None:
                break
            messages.append(Message(role="user", content=f"Customer replied: {answer}"))
    return _finish(
        env,
        outcome=outcome,
        turns=turns,
        steps=steps,
        messages=messages,
        tool_calls=tool_calls,
        retrieved=retrieved,
        usage=usage,
        llm_ms=llm_ms,
        error=error,
    )


class ToolBox:
    """What an external agent gets for one turn: the ticket, the knowledge and the tools.

    Each call goes through the same connector stack as the reference agent: permission guard,
    policy monitor, resilience and fault injection. Thus, the platform evaluates an external
    agent with the same rules and the same evidence.
    """

    def __init__(
        self,
        env: _Env,
        agent: SupportAgent,
        turn: int,
        knowledge: list[RetrievedChunk],
        customer_replies: list[str],
        max_calls: int,
    ) -> None:
        self._env, self._agent, self._turn = env, agent, turn
        self.ticket = env.case.ticket
        self.company = env.tenant.company
        self.today = env.case.now.date()
        self.knowledge = list(knowledge)
        self.customer_replies = list(customer_replies)
        self.records: list[ToolCallRecord] = []
        self.retrieved: list[RetrievedChunk] = []
        self.outcome: TurnOutcome | None = None
        self._max_calls = max_calls
        self._turn_result = TurnResult(outcome=TurnOutcome.BUDGET_EXHAUSTED, steps=0)

    def tools(self) -> list[dict[str, Any]]:
        """Tool definitions in the OpenAI function format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._agent.tools
        ]

    def call(self, name: str, **args: Any) -> dict[str, Any]:
        if self.outcome is not None:
            return {"error": {"code": "INVALID_ARGUMENT", "message": "the turn has ended"}}
        if len(self.records) >= self._max_calls:
            self.outcome = TurnOutcome.BUDGET_EXHAUSTED
            return {"error": {"code": "INVALID_ARGUMENT", "message": "the call budget is used"}}
        call = ToolCall(
            id=f"x{len(self.records)}",
            name=name,
            arguments=args,
            raw_arguments=json.dumps(args, default=str),
        )
        messages: list[Message] = []
        terminal = self._agent._run_tools(
            (call,), messages, self._env.ctx, self._env.clock.now(), self._turn, self._turn_result
        )
        self.records = list(self._turn_result.tool_calls)
        self.retrieved = list(self._turn_result.retrieved)
        if terminal is not None:
            self.outcome = terminal
        payload: dict[str, Any] = json.loads(messages[-1].content)
        return payload

    def search_kb(self, query: str) -> list[dict[str, Any]]:
        self.call("search_kb", query=query)
        return [c.model_dump(mode="json") for c in self._turn_result.retrieved[-10:]]


ExternalAgent = Callable[[ToolBox], None]


def run_external_episode(
    case: Case,
    tenant: Tenant,
    config: AgentConfig,
    agent_fn: ExternalAgent,
    trial: int,
    faults: Sequence[FaultRule] = (),
    retriever: Retriever | None = None,
    max_calls_per_turn: int = 20,
) -> EpisodeResult:
    """Run an external Python agent on one case. ``agent_fn`` is called once for each turn."""
    env = _build_env(case, tenant, config, trial, faults, retriever)
    helper = SupportAgent(config, _NoModel(), env.registry, env.retriever, env.tracer)
    tool_calls: list[ToolCallRecord] = []
    retrieved: list[RetrievedChunk] = []
    replies: list[str] = []
    outcome = TurnOutcome.BUDGET_EXHAUSTED
    error: str | None = None
    turns = 0
    with env.tracer.span(
        SpanKind.AGENT,
        "external-episode",
        **{
            "fdeops.case_id": case.id,
            "fdeops.trial": trial,
            "fdeops.agent": getattr(agent_fn, "__name__", "external"),
        },
    ):
        auto = _initial_context(env, helper) or []
        retrieved.extend(auto)
        for turn in range(1, config.max_turns + 1):
            turns = turn
            box = ToolBox(env, helper, turn, auto, replies, max_calls_per_turn)
            with env.tracer.span(SpanKind.TURN, f"turn {turn}"):
                try:
                    agent_fn(box)
                except Exception as e:  # the agent under test can fail; the run must not
                    error = f"{type(e).__name__}: {e}"
            tool_calls += box.records
            retrieved += box.retrieved
            outcome = box.outcome or (
                TurnOutcome.MODEL_ERROR if error else TurnOutcome.BUDGET_EXHAUSTED
            )
            if outcome != TurnOutcome.CLARIFY:
                break
            answer = _customer_answer(env, box.records)
            if answer is None:
                break
            replies.append(answer)
    messages = [
        Message(role="user", content=_ticket_message(case, auto)),
        *(Message(role="user", content=f"Customer replied: {r}") for r in replies),
    ]
    return _finish(
        env,
        outcome=outcome,
        turns=turns,
        steps=len(tool_calls),
        messages=messages,
        tool_calls=tool_calls,
        retrieved=retrieved,
        usage=Usage(),
        llm_ms=0.0,
        error=error,
    )


class _NoModel:
    provider = "external"

    def complete(self, request: Any) -> Any:  # pragma: no cover - never called
        raise RuntimeError("an external agent does not use the reference model")
