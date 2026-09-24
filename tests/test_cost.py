from __future__ import annotations

from competitor_intel.config import Config
from competitor_intel.cost import CostTracker, usage_from_crew
from competitor_intel.models import TokenUsage


class _FakeUsageMetrics:
    prompt_tokens = 1000
    completion_tokens = 500
    total_tokens = 1500
    cached_prompt_tokens = 0
    cache_creation_tokens = 0
    successful_requests = 1


def test_usage_from_crew_reads_attributes():
    usage = usage_from_crew(_FakeUsageMetrics())
    assert usage.prompt_tokens == 1000
    assert usage.completion_tokens == 500
    assert usage.total_tokens == 1500


def test_usage_from_crew_reads_mapping_and_none():
    usage = usage_from_crew({"prompt_tokens": 5, "total_tokens": 5})
    assert usage.prompt_tokens == 5
    assert usage_from_crew(None).total_tokens == 0


def test_cost_tracker_estimates_and_aggregates():
    config = Config(model="claude-sonnet-4-5")  # (3.0, 15.0) per 1M
    tracker = CostTracker(config)
    tracker.record("summarizer", TokenUsage(prompt_tokens=1_000_000, completion_tokens=1_000_000))
    tracker.record("analyst", TokenUsage(prompt_tokens=0, completion_tokens=100_000))

    report = tracker.report()
    assert len(report.entries) == 2
    # 3.0 + 15.0 = 18.0 for the first, 1.5 for the second (0.1M * 15).
    assert abs(report.entries[0].cost_usd - 18.0) < 1e-6
    assert abs(report.entries[1].cost_usd - 1.5) < 1e-6
    assert abs(report.total_cost_usd - 19.5) < 1e-6
    assert report.total_usage.completion_tokens == 1_100_000


def test_unknown_model_prefix_matches_pricing():
    config = Config(model="claude-sonnet-4-5-20250929")
    tracker = CostTracker(config)
    entry = tracker.record("x", TokenUsage(prompt_tokens=1_000_000))
    assert entry.cost_usd == 3.0
