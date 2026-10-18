import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

from fdeops.agent.config import AgentConfig, ModelRef
from fdeops.llm.scripted import ScriptedLLM
from fdeops.llm.types import LLMRequest, ToolCall
from fdeops.tenancy.loader import Tenant, load_tenant
from fdeops.world.cases import Case

LEDGERLOOP = Path(__file__).parents[2] / "tenants" / "ledgerloop"


@pytest.fixture(scope="session")
def tenant() -> Tenant:
    return load_tenant(LEDGERLOOP)


@pytest.fixture(scope="session")
def cases(tenant: Tenant) -> list[Case]:
    ds = tenant.build_datasets("support-core")
    return [*ds["dev"].cases, *ds["test"].cases]


def first(cases: list[Case], scenario: str) -> Case:
    return next(c for c in cases if c.scenario == scenario)


@pytest.fixture
def config() -> AgentConfig:
    return AgentConfig(id="test-agent", model=ModelRef(provider="scripted", name="script"))


def call(name: str, **args: Any) -> ToolCall:
    return ToolCall(id=f"c_{name}", name=name, arguments=args, raw_arguments=json.dumps(args))


def tool_results(req: LLMRequest) -> list[dict[str, Any]]:
    return [json.loads(m.content) for m in req.messages if m.role == "tool"]


def script(steps: Sequence[Callable[[LLMRequest], Any]]) -> ScriptedLLM:
    """Step i runs when the request carries i assistant messages so far."""

    def responder(req: LLMRequest) -> Any:
        n = sum(1 for m in req.messages if m.role == "assistant")
        return steps[min(n, len(steps) - 1)](req)

    return ScriptedLLM(responder)
