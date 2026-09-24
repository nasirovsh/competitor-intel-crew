from __future__ import annotations

import pytest
from pydantic import ValidationError

from competitor_intel.models import (
    CompetitorPage,
    FaithfulnessReport,
    ScrapeStatus,
    TokenUsage,
)


def test_page_usable_requires_ok_and_quality():
    page = CompetitorPage(url="https://x.test", status=ScrapeStatus.OK, quality_ok=True)
    assert page.usable()

    page.quality_ok = False
    assert not page.usable()

    page.quality_ok = True
    page.status = ScrapeStatus.LOW_QUALITY
    assert not page.usable()


def test_token_usage_add_is_elementwise():
    a = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15, successful_requests=1)
    b = TokenUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5, successful_requests=1)
    total = a.add(b)
    assert total.prompt_tokens == 13
    assert total.completion_tokens == 7
    assert total.total_tokens == 20
    assert total.successful_requests == 2


def test_faithfulness_score_bounds_enforced():
    with pytest.raises(ValidationError):
        FaithfulnessReport(url="https://x.test", score=1.5, passed=True)
