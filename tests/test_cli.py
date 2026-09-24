from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

import competitor_intel.runner as runner_mod
from competitor_intel.cli import app
from competitor_intel.models import (
    CompetitiveInsights,
    CompetitorPage,
    CostReport,
    RunReport,
    ScrapeStatus,
    TokenUsage,
)

runner = CliRunner()


def _fake_run(urls, config, **_kw):
    return RunReport(
        seed_urls=list(urls),
        pages=[
            CompetitorPage(url=urls[0], status=ScrapeStatus.OK, quality_ok=True, word_count=200)
        ],
        insights=CompetitiveInsights(overview="ok"),
        cost=CostReport(
            model=config.bare_model,
            total_usage=TokenUsage(total_tokens=123),
            total_cost_usd=0.02,
        ),
        decisions=["scrape: usable"],
    )


def test_cli_run_writes_reports(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(runner_mod, "run", _fake_run)

    result = runner.invoke(
        app,
        [
            "run",
            "--url",
            "https://acme.example.com/pricing",
            "--output",
            str(tmp_path),
            "--model",
            "gpt-4o-mini",
            "--provider",
            "openai",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "report.json").exists()
    assert "Estimated cost" in result.output


def test_cli_requires_url():
    result = runner.invoke(app, ["run"])
    assert result.exit_code != 0
