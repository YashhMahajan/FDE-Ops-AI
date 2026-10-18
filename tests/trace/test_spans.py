from datetime import UTC, datetime

import pytest

from fdeops.core.clock import FakeClock
from fdeops.trace.cost import PriceTable, estimate_cost
from fdeops.trace.spans import SpanKind, Tracer


def tracer() -> tuple[Tracer, FakeClock]:
    clock = FakeClock(datetime(2026, 9, 15, tzinfo=UTC))
    return Tracer("trc_1", clock), clock


def test_nesting_parent_ids() -> None:
    t, clock = tracer()
    with t.span(SpanKind.AGENT, "episode") as root:
        with t.span(SpanKind.LLM, "call", **{"gen_ai.request.model": "m"}) as child:
            clock.advance(2)
        with t.span(SpanKind.TOOL, "lookup"):
            pass
    trace = t.trace()
    assert [s.name for s in trace.spans] == ["episode", "call", "lookup"]
    assert child.parent_id == root.span_id
    assert trace.children(root.span_id) == [trace.spans[1], trace.spans[2]]
    assert child.attributes["gen_ai.request.model"] == "m"
    assert child.duration_ms == 2000
    assert trace.by_kind(SpanKind.TOOL)[0].name == "lookup"


def test_exception_marks_error_and_reraises() -> None:
    t, _ = tracer()
    with pytest.raises(RuntimeError), t.span(SpanKind.TOOL, "bad"):
        raise RuntimeError("nope")
    span = t.trace().spans[0]
    assert span.status == "error" and "nope" in (span.error or "")
    assert span.end is not None


def test_set_attributes_after_open() -> None:
    t, _ = tracer()
    with t.span(SpanKind.LLM, "x") as s:
        s.set(**{"gen_ai.usage.input_tokens": 5})
    assert t.trace().spans[0].attributes["gen_ai.usage.input_tokens"] == 5


def test_cost_basis_selection() -> None:
    table = PriceTable(api_prices={"hosted-x": (3.0, 15.0)}, gpu_usd_per_hour=0.50)
    api = estimate_cost("hosted-x", 1_000_000, 100_000, 900, table)
    assert api.basis == "api_price" and api.usd == pytest.approx(3.0 + 1.5)
    gpu = estimate_cost("qwen-local", 10, 10, 3600_000, table, self_hosted=True)
    assert gpu.basis == "gpu_time" and gpu.usd == pytest.approx(0.50)
    unknown = estimate_cost("mystery", 0, 0, 10, table)
    assert unknown.basis == "unknown" and unknown.usd == 0.0
