"""Cost estimates with an explicit basis.

Hosted models are priced per token. Self-hosted open models have no per-token price; their cost is
GPU time at an assumed hourly rate, which is an estimate and is labeled as one.
"""

from typing import Literal

from fdeops.core.model import FrozenModel


class PriceTable(FrozenModel):
    api_prices: dict[str, tuple[float, float]] = {}
    """model -> (USD per million input tokens, USD per million output tokens)"""
    gpu_usd_per_hour: float = 0.0


class CostEstimate(FrozenModel):
    usd: float
    basis: Literal["api_price", "gpu_time", "unknown"]


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: float,
    table: PriceTable,
    self_hosted: bool = False,
) -> CostEstimate:
    if model in table.api_prices:
        p_in, p_out = table.api_prices[model]
        usd = input_tokens / 1e6 * p_in + output_tokens / 1e6 * p_out
        return CostEstimate(usd=usd, basis="api_price")
    if self_hosted and table.gpu_usd_per_hour > 0:
        return CostEstimate(usd=latency_ms / 3_600_000 * table.gpu_usd_per_hour, basis="gpu_time")
    return CostEstimate(usd=0.0, basis="unknown")
