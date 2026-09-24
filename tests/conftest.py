"""Shared pytest fixtures. Everything here runs fully offline."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from competitor_intel.cache import DiskCache
from competitor_intel.config import Config
from competitor_intel.scraper import Scraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text("utf-8")


# Map request URLs -> (status_code, fixture file). Covers two competitor sites
# plus their robots.txt.
_ROUTES: dict[str, tuple[int, str]] = {
    "https://acme.example.com/pricing": (200, "acme_pricing.html"),
    "https://acme.example.com/robots.txt": (200, "robots.txt"),
    "https://beta.example.com/": (200, "beta_home.html"),
    "https://beta.example.com/pricing": (200, "beta_pricing.html"),
    "https://beta.example.com/features": (200, "beta_pricing.html"),
    "https://beta.example.com/robots.txt": (200, "robots.txt"),
    "https://junk.example.com/": (200, "junk.html"),
    "https://junk.example.com/robots.txt": (404, ""),
}


def _handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url in _ROUTES:
        status, fixture = _ROUTES[url]
        body = load_fixture(fixture) if fixture else "not found"
        return httpx.Response(status, text=body)
    if url.endswith("/robots.txt"):
        return httpx.Response(404, text="")
    return httpx.Response(404, text="not found")


@pytest.fixture
def mock_client() -> httpx.Client:
    transport = httpx.MockTransport(_handler)
    return httpx.Client(transport=transport, follow_redirects=True)


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        cache_dir=tmp_path / "cache",
        requests_per_second=0.0,  # no sleeping in tests
        min_content_words=40,
        max_scrape_attempts=2,
        faithfulness_threshold=0.7,
        max_revision_attempts=2,
    )


@pytest.fixture
def scraper(config: Config, mock_client: httpx.Client, tmp_path: Path) -> Scraper:
    cache = DiskCache(config.cache_dir, ttl_seconds=config.cache_ttl_seconds)
    return Scraper(config, cache=cache, client=mock_client)
