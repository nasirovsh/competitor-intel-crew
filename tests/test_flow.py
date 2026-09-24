"""End-to-end orchestrator tests - fully offline with fake LLM services."""

from __future__ import annotations

from competitor_intel.cost import CostTracker
from competitor_intel.flow import CompetitorIntelFlow
from competitor_intel.models import (
    ComparisonRow,
    CompetitiveInsights,
    CompetitorPage,
    CompetitorSummary,
    FaithfulnessReport,
    PricingTier,
    TokenUsage,
)
from competitor_intel.scraper import Scraper


def _usage() -> TokenUsage:
    return TokenUsage(
        prompt_tokens=100, completion_tokens=50, total_tokens=150, successful_requests=1
    )


class FakeSummarizer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def __call__(self, page: CompetitorPage, feedback: str | None = None):
        self.calls.append((page.url, feedback))
        summary = CompetitorSummary(
            url=page.url,
            company_name=page.title.split(" - ")[0] or "Unknown",
            positioning="Positioned for teams.",
            pricing=[PricingTier(name="Starter", price="$29", billing_period="per month")],
            features=["dashboards"],
            confidence=0.8,
        )
        if feedback:
            summary.revision += 1
        return summary, _usage()


class FakeEvaluator:
    """Always passes."""

    def __call__(self, page: CompetitorPage, summary: CompetitorSummary):
        report = FaithfulnessReport(url=page.url, score=0.95, passed=True)
        return report, _usage()


class FlakyEvaluator:
    """Fails the first attempt per URL, then passes."""

    def __init__(self) -> None:
        self.seen: dict[str, int] = {}

    def __call__(self, page: CompetitorPage, summary: CompetitorSummary):
        count = self.seen.get(page.url, 0)
        self.seen[page.url] = count + 1
        if count == 0:
            return (
                FaithfulnessReport(
                    url=page.url,
                    score=0.4,
                    passed=False,
                    unsupported_claims=["invented enterprise price"],
                    feedback="Do not invent pricing not present in the page.",
                ),
                _usage(),
            )
        return FaithfulnessReport(url=page.url, score=0.9, passed=True), _usage()


class FailingEvaluator:
    """Never passes - used to check the best-attempt fallback."""

    def __call__(self, page: CompetitorPage, summary: CompetitorSummary):
        return (
            FaithfulnessReport(url=page.url, score=0.3, passed=False, unsupported_claims=["x"]),
            _usage(),
        )


class FakeAnalyst:
    def __init__(self) -> None:
        self.received: list[CompetitorSummary] | None = None

    def __call__(self, summaries: list[CompetitorSummary]):
        self.received = summaries
        insights = CompetitiveInsights(
            overview="Two competitors compared.",
            comparison=[
                ComparisonRow(company_name=s.company_name, entry_price="$29") for s in summaries
            ],
            recommendation="Differentiate on price.",
        )
        return insights, _usage()


def _run(scraper, urls, config, **services):
    cost = CostTracker(config)
    flow = CompetitorIntelFlow(
        seed_urls=urls,
        scraper=scraper,
        summarizer=services.get("summarizer", FakeSummarizer()),
        evaluator=services.get("evaluator", FakeEvaluator()),
        analyst=services.get("analyst", FakeAnalyst()),
        config=config,
        cost_tracker=cost,
    )
    flow.kickoff()
    return flow.state, cost


def test_happy_path_produces_insights(scraper: Scraper, config):
    state, cost = _run(scraper, ["https://acme.example.com/pricing"], config)
    assert len(state.summaries) == 1
    assert state.insights is not None
    assert state.insights.overview
    # cost recorded for summarizer + critic + analyst
    report = cost.report()
    assert report.total_usage.total_tokens > 0
    assert any(e.label == "analyst" for e in report.entries)


def test_orchestrator_follows_link_when_landing_page_is_thin(scraper: Scraper, config):
    # beta home is too thin -> orchestrator must follow the pricing link.
    state, _ = _run(scraper, ["https://beta.example.com/"], config)
    assert state.insights is not None
    followed = any("following" in d for d in state.decisions)
    assert followed
    # The summarized page should be the richer pricing page.
    assert state.summaries[0].url == "https://beta.example.com/pricing"


def test_revision_loop_triggers_on_faithfulness_failure(scraper: Scraper, config):
    summarizer = FakeSummarizer()
    state, _ = _run(
        scraper,
        ["https://acme.example.com/pricing"],
        config,
        summarizer=summarizer,
        evaluator=FlakyEvaluator(),
    )
    # Summarizer called twice: original + one revision.
    assert len(summarizer.calls) == 2
    assert summarizer.calls[1][1] is not None  # feedback passed on revision
    assert state.summaries[0].revision == 1
    assert any("requesting revision" in d for d in state.decisions)


def test_keeps_best_attempt_when_revisions_exhausted(scraper: Scraper, config):
    state, _ = _run(
        scraper,
        ["https://acme.example.com/pricing"],
        config,
        evaluator=FailingEvaluator(),
    )
    # Still produces a summary (best attempt) and continues to analysis.
    assert len(state.summaries) == 1
    assert any("kept best attempt" in d for d in state.decisions)
    assert state.insights is not None


def test_aborts_when_no_usable_pages(scraper: Scraper, config):
    state, cost = _run(scraper, ["https://junk.example.com/"], config)
    assert state.summaries == []
    assert state.insights is None
    assert any("no usable pages" in d for d in state.decisions)
    # No LLM cost incurred when there is nothing worth analysing.
    assert cost.report().total_usage.total_tokens == 0
