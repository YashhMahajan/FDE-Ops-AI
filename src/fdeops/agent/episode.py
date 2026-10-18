"""One episode: a case, a fresh copy of the tenant's world, the agent, and a deterministic customer.

The connector stack the agent calls through, outermost first:
permission guard → policy monitor → resilience (timeouts, retries, idempotency) → fault injection
→ the domain APIs.
"""

import random
from collections.abc import Sequence
from typing import Any

from fdeops.agent.config import AgentConfig
from fdeops.agent.prompts import load_prompt
from fdeops.agent.support_agent import (
    SupportAgent,
    ToolCallRecord,
    TurnOutcome,
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
from fdeops.llm.types import LLMClient, Message, Usage
from fdeops.retrieval.retriever import RetrievedChunk, Retriever
from fdeops.tenancy.loader import Tenant
from fdeops.trace.spans import SpanKind, Trace, Tracer
from fdeops.world.cases import Case
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


def episode_seed(case_id: str, trial: int) -> int:
    return int(sha256_hex(f"{case_id}:{trial}")[:12], 16)


def _ticket_message(case: Case, chunks: list[RetrievedChunk] | None) -> str:
    t = case.ticket
    text = f"New ticket {t.ticket_id}\nFrom: {t.requester_email}\nSubject: {t.subject}\n\n{t.body}"
    if chunks is not None:
        text += "\n\n---\nKnowledge base excerpts retrieved for this ticket:\n\n" + format_chunks(
            chunks
        )
    return text


def run_episode(
    case: Case,
    tenant: Tenant,
    config: AgentConfig,
    llm: LLMClient,
    trial: int,
    faults: Sequence[FaultRule] = (),
    retriever: Retriever | None = None,
) -> EpisodeResult:
    pack = tenant.pack
    clock = FakeClock(case.now)
    seed = episode_seed(case.id, trial)
    rng = random.Random(seed)

    state: Any = tenant.base_world.copy()
    state.insert_fixtures(case.fixtures)
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
    registry = ConnectorRegistry(stack)

    tracer = Tracer(stable_id("trc", case.id, trial, config.content_hash), clock)
    retriever = retriever or Retriever(tenant.kb, config.retrieval)
    agent = SupportAgent(config, llm, registry, retriever, tracer)
    prompt = load_prompt(config.prompt_version)
    reasons = ", ".join(getattr(tenant.policy, "escalation_reasons", ()))
    ctx = OpContext(
        tenant_id=tenant.id, actor="agent", scopes=tenant.scopes, clock=clock, case_id=case.id
    )
    user_sim = pack.user_simulator()

    tool_calls: list[ToolCallRecord] = []
    retrieved: list[RetrievedChunk] = []
    usage = Usage()
    llm_ms = 0.0
    steps = turns = 0
    outcome = TurnOutcome.BUDGET_EXHAUSTED
    error: str | None = None
    with tracer.span(
        SpanKind.AGENT,
        "episode",
        **{
            "fdeops.case_id": case.id,
            "fdeops.trial": trial,
            "fdeops.agent_config": config.content_hash,
            "fdeops.prompt": prompt.hash,
        },
    ):
        auto = (
            agent.retrieve(f"{case.ticket.subject}\n{case.ticket.body}", case.now)
            if config.auto_context
            else None
        )
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
            r = agent.run_turn(messages, ctx, clock.now(), turn, seed + turn)
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
            question = next(
                (
                    c.args or {}
                    for c in reversed(r.tool_calls)
                    if c.op == "ask_clarifying_question" and c.ok
                ),
                {},
            )
            answer = user_sim.respond(case, str(question.get("question", "")))
            if answer is None:
                break
            clock.advance(60)
            pack.add_customer_reply(state, case.ticket.ticket_id, answer, clock.now())
            messages.append(Message(role="user", content=f"Customer replied: {answer}"))

    first_clarify = next(
        (i for i, c in enumerate(tool_calls) if c.op == "ask_clarifying_question" and c.ok), None
    )
    first_action = next(
        (i for i, c in enumerate(tool_calls) if c.ok and c.mutating and c.terminal is None),
        None,
    )
    agent_msgs = tuple(pack.agent_messages(state, case.ticket.ticket_id))
    return EpisodeResult(
        case_id=case.id,
        trial=trial,
        outcome=outcome,
        turns=turns,
        steps=steps,
        changes=tuple(diff_states(before, state)),
        transcript=tuple(messages),
        tool_calls=tuple(tool_calls),
        retrieved=tuple(retrieved),
        violations=tuple(v for m in monitors for v in m.violations),
        blocked=tuple(v for m in monitors for v in m.blocked),
        faults_injected=tuple(f for c in faulty for f in c.injected),
        agent_messages=agent_msgs,
        final_message=agent_msgs[-1] if agent_msgs else "",
        clarified_before_action=first_clarify is not None
        and (first_action is None or first_clarify < first_action),
        usage=usage,
        llm_latency_ms=llm_ms,
        tool_latency_ms=sum(c.latency_ms for c in tool_calls),
        audit_ok=audit.verify() is None,
        trace=tracer.trace(),
        error=error,
    )
