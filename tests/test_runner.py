from __future__ import annotations

import pytest

from competitor_intel.runner import run
from competitor_intel.scraper import Scraper
from tests.test_flow import FakeAnalyst, FakeEvaluator, FakeSummarizer


def test_run_assembles_full_report(scraper: Scraper, config):
    report = run(
        ["https://acme.example.com/pricing"],
        config,
        scraper=scraper,
        summarizer=FakeSummarizer(),
        evaluator=FakeEvaluator(),
        analyst=FakeAnalyst(),
    )
    assert report.seed_urls == ["https://acme.example.com/pricing"]
    assert len(report.pages) == 1
    assert len(report.summaries) == 1
    assert report.insights is not None
    assert report.cost is not None
    assert report.cost.total_usage.total_tokens > 0
    assert report.finished_at is not None
    assert report.decisions


def test_run_requires_urls(config):
    with pytest.raises(ValueError):
        run([], config)
