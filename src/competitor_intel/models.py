"""Pydantic models for every inter-agent output.

Each hand-off between components in the crew (scraper -> summarizer ->
evaluator -> analyst) is a typed Pydantic model rather than free text. This
keeps outputs machine-checkable and lets the orchestrator make decisions on
structured fields (quality flags, faithfulness scores, and so on).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ScrapeStatus(StrEnum):
    """Outcome of a single fetch attempt."""

    OK = "ok"
    BLOCKED_BY_ROBOTS = "blocked_by_robots"
    HTTP_ERROR = "http_error"
    LOW_QUALITY = "low_quality"
    ERROR = "error"


class CompetitorPage(BaseModel):
    """A fetched and cleaned competitor web page."""

    url: str = Field(description="The URL that was requested.")
    final_url: str = Field(default="", description="URL after redirects.")
    title: str = Field(default="", description="Page <title> text.")
    text: str = Field(default="", description="Cleaned, visible page text.")
    links: list[str] = Field(default_factory=list, description="Absolute links found on the page.")
    word_count: int = Field(default=0, description="Number of words in `text`.")
    status: ScrapeStatus = Field(default=ScrapeStatus.OK)
    quality_ok: bool = Field(
        default=False, description="Whether the content passed the quality gate."
    )
    from_cache: bool = Field(default=False)
    fetched_at: datetime = Field(default_factory=_utcnow)
    notes: list[str] = Field(default_factory=list)

    def usable(self) -> bool:
        return self.status == ScrapeStatus.OK and self.quality_ok


class PricingTier(BaseModel):
    """A single pricing plan extracted from a competitor page."""

    name: str = Field(description="Plan name, e.g. 'Pro'.")
    price: str = Field(
        default="unknown",
        description="Price as shown, e.g. '$29' or 'Contact sales'.",
    )
    billing_period: str = Field(
        default="unknown", description="e.g. 'per month', 'per user/month'."
    )
    highlights: list[str] = Field(
        default_factory=list, description="Notable inclusions for this tier."
    )


class CompetitorSummary(BaseModel):
    """A structured summary of one competitor, grounded in a scraped page."""

    url: str
    company_name: str = Field(default="unknown")
    positioning: str = Field(default="", description="One or two sentences on market positioning.")
    target_audience: str = Field(default="")
    pricing: list[PricingTier] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    notable_quotes: list[str] = Field(
        default_factory=list, description="Verbatim marketing claims from the page."
    )
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Model self-reported confidence."
    )
    revision: int = Field(default=0, description="How many revision passes produced this summary.")


class FaithfulnessReport(BaseModel):
    """Judgement on whether a summary is faithful to its source page."""

    url: str
    score: float = Field(
        ge=0.0, le=1.0, description="0 = fabricated, 1 = fully grounded in source."
    )
    passed: bool = Field(description="Whether the score cleared the threshold.")
    unsupported_claims: list[str] = Field(
        default_factory=list,
        description="Claims in the summary not supported by the source.",
    )
    feedback: str = Field(default="", description="Actionable critique used to drive a revision.")


class ComparisonRow(BaseModel):
    """One competitor's row in the side-by-side comparison table."""

    company_name: str
    entry_price: str = Field(default="unknown")
    positioning: str = Field(default="")
    standout_features: list[str] = Field(default_factory=list)


class CompetitiveInsights(BaseModel):
    """Cross-competitor analysis synthesised from all summaries."""

    overview: str = Field(default="")
    comparison: list[ComparisonRow] = Field(default_factory=list)
    differentiators: list[str] = Field(default_factory=list)
    market_gaps: list[str] = Field(default_factory=list)
    threats: list[str] = Field(default_factory=list)
    recommendation: str = Field(default="")


class TokenUsage(BaseModel):
    """Token accounting for one or more LLM calls."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_prompt_tokens: int = 0
    cache_creation_tokens: int = 0
    successful_requests: int = 0

    def add(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cached_prompt_tokens=self.cached_prompt_tokens + other.cached_prompt_tokens,
            cache_creation_tokens=self.cache_creation_tokens + other.cache_creation_tokens,
            successful_requests=self.successful_requests + other.successful_requests,
        )


class AgentCost(BaseModel):
    """Per-agent token usage and estimated dollar cost for a run."""

    label: str
    model: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    cost_usd: float = 0.0


class CostReport(BaseModel):
    """Aggregated per-run token and cost accounting."""

    model: str
    entries: list[AgentCost] = Field(default_factory=list)
    total_usage: TokenUsage = Field(default_factory=TokenUsage)
    total_cost_usd: float = 0.0


class RunReport(BaseModel):
    """The complete, serialisable result of one competitor-intelligence run."""

    seed_urls: list[str]
    pages: list[CompetitorPage] = Field(default_factory=list)
    summaries: list[CompetitorSummary] = Field(default_factory=list)
    faithfulness: list[FaithfulnessReport] = Field(default_factory=list)
    insights: CompetitiveInsights | None = None
    cost: CostReport | None = None
    decisions: list[str] = Field(
        default_factory=list, description="Orchestrator decision log for the run."
    )
    started_at: datetime = Field(default_factory=_utcnow)
    finished_at: datetime | None = None
