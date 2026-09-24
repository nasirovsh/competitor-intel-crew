"""Pure decision helpers used by the orchestrator.

These functions contain the deterministic logic behind the orchestrator's
choices - "is this scraped content junk?", "which internal link should I follow
instead?", "does this summary pass the faithfulness bar?". Keeping them pure
makes the orchestrator's decisions cheap to unit-test without any LLM or
network access.
"""

from __future__ import annotations

from urllib.parse import urlparse

from .models import CompetitorPage, FaithfulnessReport

# Anchor/URL keywords that suggest a more information-rich page to follow when a
# landing page turns out to be thin on pricing/feature content.
FOLLOW_KEYWORDS: tuple[str, ...] = (
    "pricing",
    "plans",
    "price",
    "features",
    "product",
    "compare",
    "solutions",
)

# Substrings that strongly suggest an error / placeholder page.
JUNK_MARKERS: tuple[str, ...] = (
    "enable javascript",
    "access denied",
    "are you a robot",
    "captcha",
    "404 not found",
    "page not found",
)


def assess_content(page: CompetitorPage, min_words: int) -> tuple[bool, list[str]]:
    """Return ``(is_ok, reasons)`` for a fetched page's content quality."""
    reasons: list[str] = []
    if page.word_count < min_words:
        reasons.append(f"thin content: {page.word_count} words < {min_words} minimum")
    lowered = page.text.lower()
    for marker in JUNK_MARKERS:
        if marker in lowered:
            reasons.append(f"junk marker detected: '{marker}'")
    return (len(reasons) == 0, reasons)


def select_followup_link(page: CompetitorPage, visited: set[str]) -> str | None:
    """Pick the most promising unvisited internal link to follow, or ``None``.

    Prefers same-host links whose path contains a high-signal keyword such as
    ``pricing`` or ``features``. This is the concrete mechanism behind the
    orchestrator's "which pages to follow" decision.
    """
    base_host = urlparse(page.final_url or page.url).netloc
    best: tuple[int, str] | None = None
    for link in page.links:
        if link in visited:
            continue
        parsed = urlparse(link)
        if parsed.scheme not in {"http", "https"}:
            continue
        if base_host and parsed.netloc and parsed.netloc != base_host:
            continue  # stay on the same competitor's site
        haystack = f"{parsed.path} {parsed.query}".lower()
        score = sum(kw in haystack for kw in FOLLOW_KEYWORDS)
        if score == 0:
            continue
        if best is None or score > best[0]:
            best = (score, link)
    return best[1] if best else None


def faithfulness_passes(report: FaithfulnessReport, threshold: float) -> bool:
    """Whether a faithfulness report clears the configured threshold."""
    return report.score >= threshold and not report.unsupported_claims
