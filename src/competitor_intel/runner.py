"""High-level entry point: wire config -> services -> flow -> report."""

from __future__ import annotations

from datetime import UTC, datetime

from .config import Config, load_config
from .cost import CostTracker
from .crew import (
    AnalystService,
    CrewAnalyst,
    CrewEvaluator,
    CrewSummarizer,
    EvaluatorService,
    SummarizerService,
)
from .flow import CompetitorIntelFlow
from .models import RunReport
from .scraper import Scraper


def run(
    urls: list[str],
    config: Config | None = None,
    *,
    scraper: Scraper | None = None,
    summarizer: SummarizerService | None = None,
    evaluator: EvaluatorService | None = None,
    analyst: AnalystService | None = None,
) -> RunReport:
    """Run the competitor-intelligence flow over ``urls`` and return a report.

    All LLM-backed collaborators can be injected (used by tests to run offline);
    when omitted, the real CrewAI-backed services are constructed.
    """
    if not urls:
        raise ValueError("at least one URL is required")

    config = config or load_config()
    cost_tracker = CostTracker(config)

    scraper = scraper or Scraper(config)
    summarizer = summarizer or CrewSummarizer(config)
    evaluator = evaluator or CrewEvaluator(config)
    analyst = analyst or CrewAnalyst(config)

    flow = CompetitorIntelFlow(
        seed_urls=urls,
        scraper=scraper,
        summarizer=summarizer,
        evaluator=evaluator,
        analyst=analyst,
        config=config,
        cost_tracker=cost_tracker,
    )
    flow.kickoff()
    state = flow.state

    return RunReport(
        seed_urls=list(urls),
        pages=state.pages,
        summaries=state.summaries,
        faithfulness=state.faithfulness,
        insights=state.insights,
        cost=cost_tracker.report(),
        decisions=state.decisions,
        finished_at=datetime.now(UTC),
    )
