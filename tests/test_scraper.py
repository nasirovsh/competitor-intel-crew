from __future__ import annotations

import httpx

from competitor_intel.config import Config
from competitor_intel.models import ScrapeStatus
from competitor_intel.scraper import Scraper, clean_html
from tests.conftest import load_fixture


def test_clean_html_strips_boilerplate_and_keeps_content():
    html = load_fixture("acme_pricing.html")
    title, text, _links = clean_html(html, "https://acme.example.com/pricing")
    assert title == "Acme Analytics - Pricing"
    assert "tracking" not in text  # <script> removed
    assert "Home" not in text  # <nav> removed
    assert "Privacy" not in text  # <footer> removed
    assert "Starter" in text and "$29 per month" in text


def test_clean_html_extracts_absolute_links_from_content():
    html = load_fixture("beta_home.html")
    _title, _text, links = clean_html(html, "https://beta.example.com/")
    assert "https://beta.example.com/pricing" in links
    assert "https://beta.example.com/features" in links


def test_fetch_good_page_is_usable(scraper: Scraper):
    page = scraper.fetch("https://acme.example.com/pricing")
    assert page.status == ScrapeStatus.OK
    assert page.usable()
    assert page.word_count > 40
    assert not page.from_cache


def test_fetch_uses_cache_second_time(scraper: Scraper):
    first = scraper.fetch("https://acme.example.com/pricing")
    assert not first.from_cache
    second = scraper.fetch("https://acme.example.com/pricing")
    assert second.from_cache
    assert second.title == first.title


def test_junk_page_flagged_low_quality(scraper: Scraper):
    page = scraper.fetch("https://junk.example.com/")
    assert not page.usable()
    assert page.status == ScrapeStatus.LOW_QUALITY
    assert page.notes  # has reasons


def test_robots_disallows_private_path():
    config = Config(requests_per_second=0.0, respect_robots=True, cache_enabled=False)
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda req: (
                httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
                if req.url.path == "/robots.txt"
                else httpx.Response(200, text="secret")
            )
        ),
        follow_redirects=True,
    )
    scraper = Scraper(config, client=client)
    assert scraper.can_fetch("https://site.test/public") is True
    assert scraper.can_fetch("https://site.test/private/data") is False

    blocked = scraper.fetch("https://site.test/private/data")
    assert blocked.status == ScrapeStatus.BLOCKED_BY_ROBOTS


def test_http_error_is_captured(scraper: Scraper):
    page = scraper.fetch("https://acme.example.com/missing")
    assert page.status == ScrapeStatus.HTTP_ERROR
    assert not page.usable()
