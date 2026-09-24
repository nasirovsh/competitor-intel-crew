"""Per-run token and cost tracking.

Every LLM-backed step reports its token usage; the tracker accumulates usage per
agent label and estimates a dollar cost from the configured model's list price.
The result is surfaced directly in the run report.
"""

from __future__ import annotations

from typing import Any

from .config import Config
from .models import AgentCost, CostReport, TokenUsage


def usage_from_crew(raw: Any) -> TokenUsage:
    """Convert a CrewAI ``UsageMetrics`` (or mapping) into our ``TokenUsage``."""
    if raw is None:
        return TokenUsage()
    if isinstance(raw, TokenUsage):
        return raw

    def pick(name: str) -> int:
        if isinstance(raw, dict):
            return int(raw.get(name, 0) or 0)
        return int(getattr(raw, name, 0) or 0)

    return TokenUsage(
        prompt_tokens=pick("prompt_tokens"),
        completion_tokens=pick("completion_tokens"),
        total_tokens=pick("total_tokens"),
        cached_prompt_tokens=pick("cached_prompt_tokens"),
        cache_creation_tokens=pick("cache_creation_tokens"),
        successful_requests=pick("successful_requests"),
    )


class CostTracker:
    """Accumulates token usage across a run and estimates cost."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._entries: list[AgentCost] = []

    def _estimate(self, usage: TokenUsage) -> float:
        in_price, out_price = self.config.pricing()
        cost = (usage.prompt_tokens / 1_000_000) * in_price
        cost += (usage.completion_tokens / 1_000_000) * out_price
        return round(cost, 6)

    def record(self, label: str, usage: TokenUsage) -> AgentCost:
        entry = AgentCost(
            label=label,
            model=self.config.bare_model,
            usage=usage,
            cost_usd=self._estimate(usage),
        )
        self._entries.append(entry)
        return entry

    def report(self) -> CostReport:
        total = TokenUsage()
        total_cost = 0.0
        for entry in self._entries:
            total = total.add(entry.usage)
            total_cost += entry.cost_usd
        return CostReport(
            model=self.config.bare_model,
            entries=list(self._entries),
            total_usage=total,
            total_cost_usd=round(total_cost, 6),
        )
