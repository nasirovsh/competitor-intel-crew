from __future__ import annotations

from competitor_intel.models import CompetitorPage, FaithfulnessReport
from competitor_intel.quality import (
    assess_content,
    faithfulness_passes,
    select_followup_link,
)


def _page(**kw) -> CompetitorPage:
    return CompetitorPage(url="https://x.test", **kw)


def test_assess_content_flags_thin_content():
    page = _page(text="too short", word_count=2)
    ok, reasons = assess_content(page, min_words=40)
    assert not ok
    assert any("thin content" in r for r in reasons)


def test_assess_content_flags_junk_marker():
    page = _page(
        text="Please enable JavaScript to view this site " + "word " * 60,
        word_count=100,
    )
    ok, reasons = assess_content(page, min_words=40)
    assert not ok
    assert any("junk marker" in r for r in reasons)


def test_assess_content_passes_good_page():
    page = _page(text="word " * 100, word_count=100)
    ok, reasons = assess_content(page, min_words=40)
    assert ok
    assert reasons == []


def test_select_followup_prefers_pricing_link():
    page = _page(
        final_url="https://beta.example.com/",
        links=[
            "https://beta.example.com/about",
            "https://beta.example.com/pricing",
            "https://twitter.com/betaboard",
        ],
    )
    chosen = select_followup_link(page, visited={"https://beta.example.com/"})
    assert chosen == "https://beta.example.com/pricing"


def test_select_followup_skips_offsite_and_visited():
    page = _page(
        final_url="https://beta.example.com/",
        links=[
            "https://other.example.com/pricing",  # off-site
            "https://beta.example.com/pricing",  # already visited
        ],
    )
    chosen = select_followup_link(
        page, visited={"https://beta.example.com/", "https://beta.example.com/pricing"}
    )
    assert chosen is None


def test_faithfulness_passes_requires_threshold_and_no_unsupported():
    ok = FaithfulnessReport(url="u", score=0.9, passed=True)
    assert faithfulness_passes(ok, 0.7)

    low = FaithfulnessReport(url="u", score=0.5, passed=False)
    assert not faithfulness_passes(low, 0.7)

    unsupported = FaithfulnessReport(
        url="u", score=0.95, passed=False, unsupported_claims=["made up price"]
    )
    assert not faithfulness_passes(unsupported, 0.7)
