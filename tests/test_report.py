from __future__ import annotations

from pathlib import Path

from competitor_intel.models import (
    AgentCost,
    ComparisonRow,
    CompetitiveInsights,
    CompetitorSummary,
    CostReport,
    FaithfulnessReport,
    PricingTier,
    RunReport,
    TokenUsage,
)
from competitor_intel.report import load_report, to_markdown, write_report


def _sample_report() -> RunReport:
    usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    return RunReport(
        seed_urls=["https://acme.example.com/pricing"],
        summaries=[
            CompetitorSummary(
                url="https://acme.example.com/pricing",
                company_name="Acme Analytics",
                positioning="Analytics for SaaS teams.",
                pricing=[PricingTier(name="Starter", price="$29", billing_period="per month")],
                features=["dashboards", "funnels"],
            )
        ],
        faithfulness=[
            FaithfulnessReport(url="https://acme.example.com/pricing", score=0.9, passed=True)
        ],
        insights=CompetitiveInsights(
            overview="One competitor analysed.",
            comparison=[ComparisonRow(company_name="Acme Analytics", entry_price="$29")],
            differentiators=["real-time dashboards"],
            recommendation="Compete on onboarding.",
        ),
        cost=CostReport(
            model="claude-sonnet-4-5",
            entries=[
                AgentCost(
                    label="summarizer",
                    model="claude-sonnet-4-5",
                    usage=usage,
                    cost_usd=0.01,
                )
            ],
            total_usage=usage,
            total_cost_usd=0.01,
        ),
        decisions=["scrape: usable", "analysis: done"],
    )


def test_markdown_contains_key_sections():
    md = to_markdown(_sample_report())
    assert "# Competitor Intelligence Report" in md
    assert "## Comparison" in md
    assert "Acme Analytics" in md
    assert "## Orchestrator decision log" in md
    assert "## Cost breakdown" in md
    assert "$0.01" in md


def test_write_and_load_roundtrip(tmp_path: Path):
    report = _sample_report()
    paths = write_report(report, tmp_path)
    assert paths["markdown"].exists()
    assert paths["json"].exists()

    loaded = load_report(paths["json"])
    assert loaded.seed_urls == report.seed_urls
    assert loaded.insights is not None
    assert loaded.insights.overview == "One competitor analysed."
