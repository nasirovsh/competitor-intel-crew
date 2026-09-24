"""The orchestrator, expressed as a CrewAI ``Flow``.

This is the decision-maker. It is *not* a plain sequential chain: it makes real
choices at run time and records them in a decision log.

Two genuine orchestrator decision loops live here:

1. **Which page to scrape.** If a seed URL returns thin/junk content, the
   orchestrator follows the most relevant internal link (e.g. a ``/pricing``
   page) instead, up to ``max_scrape_attempts`` times.
2. **Whether a summary is good enough.** Each summary is checked by the
   faithfulness critic; if it fails, the orchestrator sends it back for revision
   with the critic's feedback, up to ``max_revision_attempts`` times.

A ``@router`` after scraping decides whether there is enough usable material to
continue at all. All LLM-backed steps are injected as callables, so the whole
flow runs offline in tests with fakes.
"""

from __future__ import annotations

from crewai.flow.flow import Flow, listen, router, start
from pydantic import BaseModel, Field

from .config import Config
from .cost import CostTracker
from .crew import AnalystService, EvaluatorService, SummarizerService
from .models import (
    CompetitiveInsights,
    CompetitorPage,
    CompetitorSummary,
    FaithfulnessReport,
)
from .quality import select_followup_link
from .scraper import Scraper


class IntelState(BaseModel):
    """Mutable state carried through the flow."""

    urls: list[str] = Field(default_factory=list)
    pages: list[CompetitorPage] = Field(default_factory=list)
    summaries: list[CompetitorSummary] = Field(default_factory=list)
    faithfulness: list[FaithfulnessReport] = Field(default_factory=list)
    insights: CompetitiveInsights | None = None
    decisions: list[str] = Field(default_factory=list)


class CompetitorIntelFlow(Flow[IntelState]):
    """Competitor-intelligence orchestrator built on CrewAI's Flow API."""

    def __init__(
        self,
        *,
        seed_urls: list[str],
        scraper: Scraper,
        summarizer: SummarizerService,
        evaluator: EvaluatorService,
        analyst: AnalystService,
        config: Config,
        cost_tracker: CostTracker,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._seed_urls = seed_urls
        self._scraper = scraper
        self._summarizer = summarizer
        self._evaluator = evaluator
        self._analyst = analyst
        self._config = config
        self._cost = cost_tracker

    # -- decision loop 1: which page to scrape ------------------------------
    def _scrape_with_followups(self, seed_url: str) -> CompetitorPage:
        visited: set[str] = set()
        current = seed_url
        best: CompetitorPage | None = None
        for attempt in range(1, self._config.max_scrape_attempts + 1):
            visited.add(current)
            page = self._scraper.fetch(current)
            if best is None or page.word_count > best.word_count:
                best = page
            if page.usable():
                self.state.decisions.append(
                    f"scrape: '{current}' usable on attempt {attempt}"
                    + (" (cache)" if page.from_cache else "")
                )
                return page

            followup = select_followup_link(page, visited)
            if followup is None or attempt == self._config.max_scrape_attempts:
                self.state.decisions.append(
                    f"scrape: '{current}' unusable ({', '.join(page.notes) or 'no content'});"
                    " no better link to follow"
                )
                break
            self.state.decisions.append(f"scrape: '{current}' thin; following '{followup}' instead")
            current = followup

        return best if best is not None else self._scraper.fetch(seed_url)

    @start()
    def scrape_stage(self) -> str:
        self.state.urls = list(self._seed_urls)
        for seed in self.state.urls:
            self.state.pages.append(self._scrape_with_followups(seed))
        return "scraped"

    @router(scrape_stage)
    def route_after_scrape(self) -> str:
        usable = [p for p in self.state.pages if p.usable()]
        if not usable:
            self.state.decisions.append("route: no usable pages after scraping - aborting analysis")
            return "insufficient"
        self.state.decisions.append(
            f"route: {len(usable)}/{len(self.state.pages)} pages usable - proceeding"
        )
        return "sufficient"

    @listen("insufficient")
    def handle_insufficient(self) -> str:
        return "aborted"

    # -- decision loop 2: is the summary faithful enough? -------------------
    def _summarize_with_revision(self, page: CompetitorPage) -> CompetitorSummary:
        feedback: str | None = None
        summary: CompetitorSummary | None = None
        best: tuple[float, CompetitorSummary, FaithfulnessReport] | None = None

        for attempt in range(1, self._config.max_revision_attempts + 1):
            summary, s_usage = self._summarizer(page, feedback)
            self._cost.record(f"summarizer[{page.url}#{attempt}]", s_usage)

            report, e_usage = self._evaluator(page, summary)
            self._cost.record(f"critic[{page.url}#{attempt}]", e_usage)

            if best is None or report.score > best[0]:
                best = (report.score, summary, report)

            if report.passed:
                self.state.decisions.append(
                    f"summary: '{page.url}' passed faithfulness "
                    f"(score={report.score:.2f}) on attempt {attempt}"
                )
                self.state.faithfulness.append(report)
                return summary

            feedback = report.feedback or "; ".join(report.unsupported_claims)
            self.state.decisions.append(
                f"summary: '{page.url}' failed faithfulness "
                f"(score={report.score:.2f}); requesting revision {attempt}"
            )

        # Exhausted revisions: keep the best-scoring attempt.
        assert best is not None
        self.state.decisions.append(
            f"summary: '{page.url}' kept best attempt after "
            f"{self._config.max_revision_attempts} tries (score={best[0]:.2f})"
        )
        self.state.faithfulness.append(best[2])
        return best[1]

    @listen("sufficient")
    def summarize_stage(self) -> str:
        for page in self.state.pages:
            if page.usable():
                self.state.summaries.append(self._summarize_with_revision(page))
        return "summarized"

    @listen(summarize_stage)
    def analyze_stage(self) -> str:
        if not self.state.summaries:
            return "no-summaries"
        insights, usage = self._analyst(self.state.summaries)
        self._cost.record("analyst", usage)
        self.state.insights = insights
        self.state.decisions.append(
            f"analysis: synthesised insights from {len(self.state.summaries)} summaries"
        )
        return "analyzed"
