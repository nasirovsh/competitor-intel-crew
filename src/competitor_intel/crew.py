"""CrewAI agents, tasks, and single-purpose crews.

This module holds the *LLM-backed* members of the crew - the summarizer, the
faithfulness critic, and the insights analyst. Each is exposed as a small
callable "service" that takes typed input and returns a typed Pydantic output
plus its token usage, so the orchestrator can compose them and account for cost.

CrewAI is imported lazily inside the builders so that the deterministic parts of
the package (scraper, cache, cost, models) stay import-light and fast to test.
"""

from __future__ import annotations

from typing import Any, Protocol

from .config import Config
from .cost import usage_from_crew
from .models import (
    CompetitiveInsights,
    CompetitorPage,
    CompetitorSummary,
    FaithfulnessReport,
    TokenUsage,
)

# Page text handed to the LLM is capped to keep prompts (and cost) bounded.
_MAX_PAGE_CHARS = 12_000


class SummarizerService(Protocol):
    def __call__(
        self, page: CompetitorPage, feedback: str | None = None
    ) -> tuple[CompetitorSummary, TokenUsage]: ...


class EvaluatorService(Protocol):
    def __call__(
        self, page: CompetitorPage, summary: CompetitorSummary
    ) -> tuple[FaithfulnessReport, TokenUsage]: ...


class AnalystService(Protocol):
    def __call__(
        self, summaries: list[CompetitorSummary]
    ) -> tuple[CompetitiveInsights, TokenUsage]: ...


def build_llm(config: Config) -> Any:
    """Construct a CrewAI ``LLM`` for the configured provider/model."""
    from crewai import LLM

    kwargs: dict[str, Any] = {
        "model": config.model_string,
        "temperature": config.temperature,
    }
    if config.api_key:
        kwargs["api_key"] = config.api_key
    return LLM(**kwargs)


def _kickoff(crew: Any, inputs: dict[str, Any]) -> tuple[Any, TokenUsage]:
    result = crew.kickoff(inputs=inputs)
    usage = usage_from_crew(getattr(result, "token_usage", None))
    return result.pydantic, usage


def _page_excerpt(page: CompetitorPage) -> str:
    return page.text[:_MAX_PAGE_CHARS]


class CrewSummarizer:
    """Summarizer agent: extracts structured pricing/features/positioning."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def _agent(self) -> Any:
        from crewai import Agent

        return Agent(
            role="Competitor Product Summarizer",
            goal=(
                "Extract accurate, structured pricing, features, and positioning "
                "from a single competitor web page, without inventing details."
            ),
            backstory=(
                "You are a meticulous product analyst. You only report what the "
                "page actually says and mark anything absent as 'unknown'."
            ),
            llm=build_llm(self.config),
            allow_delegation=False,
            verbose=self.config.verbose,
        )

    def __call__(
        self, page: CompetitorPage, feedback: str | None = None
    ) -> tuple[CompetitorSummary, TokenUsage]:
        from crewai import Crew, Process, Task

        revision_note = ""
        if feedback:
            revision_note = (
                "\n\nA previous attempt was rejected by the faithfulness reviewer. "
                f"Fix these problems and stay strictly grounded in the source:\n{feedback}"
            )

        task = Task(
            description=(
                "Summarize the competitor page below into the structured schema. "
                "Use only information present in the text. For anything not stated, "
                "use 'unknown'. Capture pricing tiers, key features, positioning, "
                "and target audience. Include a few verbatim marketing quotes.\n\n"
                f"URL: {page.url}\n"
                f"TITLE: {page.title}\n\n"
                f"PAGE TEXT:\n{_page_excerpt(page)}"
                f"{revision_note}"
            ),
            expected_output=(
                "A CompetitorSummary with company_name, positioning, target_audience, "
                "pricing tiers, features, notable_quotes, and a confidence score."
            ),
            agent=self._agent(),
            output_pydantic=CompetitorSummary,
        )
        crew = Crew(
            agents=[task.agent],
            tasks=[task],
            process=Process.sequential,
            verbose=self.config.verbose,
        )
        summary, usage = _kickoff(crew, {"url": page.url})
        summary.url = page.url
        if feedback:
            summary.revision += 1
        return summary, usage


class CrewEvaluator:
    """Faithfulness critic: LLM-as-judge grounding check (0..1)."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def _agent(self) -> Any:
        from crewai import Agent

        return Agent(
            role="Faithfulness Critic",
            goal=(
                "Detect any claim in a competitor summary that is not supported by "
                "the source page, and score how faithful the summary is."
            ),
            backstory=(
                "You are a rigorous fact-checker. You compare each claim against the "
                "source and flag hallucinations without mercy."
            ),
            llm=build_llm(self.config),
            allow_delegation=False,
            verbose=self.config.verbose,
        )

    def __call__(
        self, page: CompetitorPage, summary: CompetitorSummary
    ) -> tuple[FaithfulnessReport, TokenUsage]:
        from crewai import Crew, Process, Task

        task = Task(
            description=(
                "Judge whether the SUMMARY is faithful to the SOURCE page. "
                "List every claim in the summary that the source does not support. "
                "Score faithfulness from 0 (fabricated) to 1 (fully grounded). "
                "Set 'passed' to true only if there are no unsupported claims and "
                f"the score is at least {self.config.faithfulness_threshold}. "
                "Give concise, actionable feedback for a revision.\n\n"
                f"SOURCE (URL {page.url}):\n{_page_excerpt(page)}\n\n"
                f"SUMMARY (JSON):\n{summary.model_dump_json(indent=2)}"
            ),
            expected_output=(
                "A FaithfulnessReport with score, passed, unsupported_claims, feedback."
            ),
            agent=self._agent(),
            output_pydantic=FaithfulnessReport,
        )
        crew = Crew(
            agents=[task.agent],
            tasks=[task],
            process=Process.sequential,
            verbose=self.config.verbose,
        )
        report, usage = _kickoff(crew, {"url": page.url})
        report.url = page.url
        report.passed = (
            report.score >= self.config.faithfulness_threshold and not report.unsupported_claims
        )
        return report, usage


class CrewAnalyst:
    """Insights analyst: synthesises cross-competitor comparison."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def _agent(self) -> Any:
        from crewai import Agent

        return Agent(
            role="Competitive Insights Analyst",
            goal=(
                "Synthesise multiple competitor summaries into a clear, actionable "
                "competitive landscape with a side-by-side comparison."
            ),
            backstory=(
                "You are a seasoned market strategist who turns raw competitor data "
                "into crisp positioning insight for a product team."
            ),
            llm=build_llm(self.config),
            allow_delegation=False,
            verbose=self.config.verbose,
        )

    def __call__(
        self, summaries: list[CompetitorSummary]
    ) -> tuple[CompetitiveInsights, TokenUsage]:
        from crewai import Crew, Process, Task

        payload = "\n\n".join(s.model_dump_json(indent=2) for s in summaries)
        task = Task(
            description=(
                "Analyse the competitor summaries below. Produce an overview, a "
                "side-by-side comparison row per competitor, shared/unique "
                "differentiators, market gaps, threats, and a recommendation. "
                "Base every statement on the provided summaries only.\n\n"
                f"SUMMARIES:\n{payload}"
            ),
            expected_output=(
                "A CompetitiveInsights object with overview, comparison rows, "
                "differentiators, market_gaps, threats, and recommendation."
            ),
            agent=self._agent(),
            output_pydantic=CompetitiveInsights,
        )
        crew = Crew(
            agents=[task.agent],
            tasks=[task],
            process=Process.sequential,
            verbose=self.config.verbose,
        )
        return _kickoff(crew, {})
