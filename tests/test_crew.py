"""Offline tests for the crew's structured-output parsing and fallbacks.

These cover the crash-hardening path: when CrewAI cannot parse the LLM output
into the expected Pydantic model, ``result.pydantic`` is ``None`` and the raw
text may be unparseable. Each caller must degrade to a clear, typed failure
instead of dereferencing ``None`` (the historical ``AttributeError``).
"""

from __future__ import annotations

import pytest

import competitor_intel.crew as crewmod
from competitor_intel.config import Config
from competitor_intel.crew import (
    _UNPARSEABLE_NOTE,
    CrewAnalyst,
    CrewEvaluator,
    CrewSummarizer,
    _insights_from_result,
    _parse_result,
    _report_from_result,
    _summary_from_result,
)
from competitor_intel.models import (
    CompetitiveInsights,
    CompetitorPage,
    CompetitorSummary,
    FaithfulnessReport,
    TokenUsage,
)


class FakeResult:
    """Stand-in for a CrewAI crew-output object."""

    def __init__(self, pydantic: object = None, raw: object = "", token_usage: object = None):
        self.pydantic = pydantic
        self.raw = raw
        self.token_usage = token_usage


@pytest.fixture
def config() -> Config:
    return Config(faithfulness_threshold=0.7)


@pytest.fixture
def page() -> CompetitorPage:
    return CompetitorPage(url="https://x.example.com/", title="X Co", text="hello world " * 30)


# -- _parse_result -----------------------------------------------------------


def test_parse_result_prefers_pydantic() -> None:
    want = CompetitorSummary(url="https://x.example.com/", company_name="X Co")
    got = _parse_result(FakeResult(pydantic=want), CompetitorSummary)
    assert got is want


def test_parse_result_recovers_from_raw_json() -> None:
    result = FakeResult(
        pydantic=None, raw='{"url": "https://x.example.com/", "score": 0.9, "passed": true}'
    )
    got = _parse_result(result, FaithfulnessReport)
    assert got is not None
    assert got.score == 0.9


def test_parse_result_recovers_json_wrapped_in_prose() -> None:
    raw = 'Sure! Here is the JSON:\n```json\n{"overview": "hi", "recommendation": "go"}\n```'
    got = _parse_result(FakeResult(pydantic=None, raw=raw), CompetitiveInsights)
    assert got is not None
    assert got.overview == "hi"


def test_parse_result_returns_none_on_garbage() -> None:
    result = FakeResult(pydantic=None, raw="not json at all")
    assert _parse_result(result, CompetitorSummary) is None


def test_parse_result_returns_none_on_empty_and_none() -> None:
    assert _parse_result(FakeResult(pydantic=None, raw=""), CompetitorSummary) is None
    assert _parse_result(None, CompetitorSummary) is None


def test_parse_result_rejects_schema_violation() -> None:
    # score out of range -> ValidationError -> None (not a crash).
    result = FakeResult(pydantic=None, raw='{"url": "u", "score": 5, "passed": true}')
    assert _parse_result(result, FaithfulnessReport) is None


# -- per-caller fallback helpers --------------------------------------------


def test_summary_from_result_falls_back() -> None:
    summary = _summary_from_result(FakeResult(pydantic=None, raw="junk"), "https://x.example.com/")
    assert isinstance(summary, CompetitorSummary)
    assert summary.url == "https://x.example.com/"
    assert summary.confidence == 0.0
    assert summary.positioning == _UNPARSEABLE_NOTE


def test_report_from_result_falls_back_as_failing() -> None:
    report = _report_from_result(FakeResult(pydantic=None, raw="junk"), "https://x.example.com/")
    assert isinstance(report, FaithfulnessReport)
    assert report.url == "https://x.example.com/"
    assert report.score == 0.0
    assert report.passed is False
    assert report.unsupported_claims  # eligible for the revision path


def test_insights_from_result_falls_back() -> None:
    insights = _insights_from_result(FakeResult(pydantic=None, raw="junk"))
    assert isinstance(insights, CompetitiveInsights)
    assert insights.overview == _UNPARSEABLE_NOTE


# -- caller __call__ with a None/unparseable result (no crash) --------------


def test_summarizer_does_not_crash_on_none(monkeypatch, config: Config, page: CompetitorPage):
    monkeypatch.setattr(crewmod, "_kickoff", lambda crew, inputs: (None, TokenUsage()))
    summary, _ = CrewSummarizer(config)(page)
    assert summary.url == page.url
    assert summary.positioning == _UNPARSEABLE_NOTE


def test_summarizer_bumps_revision_on_feedback(monkeypatch, config: Config, page: CompetitorPage):
    monkeypatch.setattr(
        crewmod, "_kickoff", lambda crew, inputs: (FakeResult(pydantic=None, raw="x"), TokenUsage())
    )
    summary, _ = CrewSummarizer(config)(page, feedback="fix it")
    assert summary.revision == 1


def test_evaluator_does_not_crash_on_none(monkeypatch, config: Config, page: CompetitorPage):
    monkeypatch.setattr(crewmod, "_kickoff", lambda crew, inputs: (None, TokenUsage()))
    summary = CompetitorSummary(url=page.url, company_name="X Co")
    report, _ = CrewEvaluator(config)(page, summary)
    assert report.url == page.url
    assert report.passed is False
    assert report.score == 0.0


def test_analyst_does_not_crash_on_none(monkeypatch, config: Config, page: CompetitorPage):
    monkeypatch.setattr(crewmod, "_kickoff", lambda crew, inputs: (None, TokenUsage()))
    insights, _ = CrewAnalyst(config)([CompetitorSummary(url=page.url)])
    assert insights.overview == _UNPARSEABLE_NOTE
