"""Polite, cached HTTP scraper that produces clean :class:`CompetitorPage`s.

Responsibilities:
- respect ``robots.txt`` (configurable),
- rate-limit per host,
- cache fetched pages on disk so development never re-scrapes,
- strip boilerplate and return clean, structured text + links.

The HTTP client is injectable so tests can run fully offline against small HTML
fixtures via ``httpx.MockTransport``.
"""

from __future__ import annotations

import time
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .cache import DiskCache
from .config import Config
from .models import CompetitorPage, ScrapeStatus
from .quality import assess_content

_STRIP_TAGS = ("script", "style", "nav", "footer", "header", "aside", "noscript", "form")


def clean_html(html: str, base_url: str) -> tuple[str, str, list[str]]:
    """Return ``(title, text, links)`` extracted from raw HTML.

    Boilerplate tags are removed, whitespace is collapsed, and links are made
    absolute. Pure and dependency-light so it is trivial to unit-test.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(list(_STRIP_TAGS)):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else ""

    text = soup.get_text(separator=" ", strip=True)
    text = " ".join(text.split())

    links: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, anchor["href"]).split("#")[0]
        if href and href not in seen:
            seen.add(href)
            links.append(href)

    return title, text, links


class Scraper:
    """Fetches and cleans competitor pages, politely and with caching."""

    def __init__(
        self,
        config: Config,
        cache: DiskCache | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self.cache = cache or DiskCache(
            config.cache_dir,
            ttl_seconds=config.cache_ttl_seconds,
            enabled=config.cache_enabled,
        )
        self._client = client or httpx.Client(
            headers={"User-Agent": config.user_agent},
            timeout=config.request_timeout,
            follow_redirects=True,
        )
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}
        self._last_request_at: dict[str, float] = {}

    # -- robots.txt ---------------------------------------------------------
    def _robots_for(self, url: str) -> robotparser.RobotFileParser | None:
        parsed = urlparse(url)
        host = f"{parsed.scheme}://{parsed.netloc}"
        if host in self._robots:
            return self._robots[host]

        parser: robotparser.RobotFileParser | None = robotparser.RobotFileParser()
        try:
            resp = self._client.get(urljoin(host, "/robots.txt"))
            if resp.status_code >= 400:
                parser = None  # no robots -> allow
            else:
                parser.parse(resp.text.splitlines())
        except httpx.HTTPError:
            parser = None
        self._robots[host] = parser
        return parser

    def can_fetch(self, url: str) -> bool:
        if not self.config.respect_robots:
            return True
        parser = self._robots_for(url)
        if parser is None:
            return True
        return parser.can_fetch(self.config.user_agent, url)

    # -- rate limiting ------------------------------------------------------
    def _respect_rate_limit(self, url: str) -> None:
        rps = self.config.requests_per_second
        if rps <= 0:
            return
        host = urlparse(url).netloc
        min_interval = 1.0 / rps
        last = self._last_request_at.get(host)
        now = time.monotonic()
        if last is not None:
            wait = min_interval - (now - last)
            if wait > 0:
                time.sleep(wait)
        self._last_request_at[host] = time.monotonic()

    # -- fetch --------------------------------------------------------------
    def fetch(self, url: str) -> CompetitorPage:
        """Fetch, clean, quality-check and cache a single URL."""
        cached = self.cache.get(url)
        if cached is not None:
            page = CompetitorPage.model_validate(cached)
            page.from_cache = True
            return page

        if not self.can_fetch(url):
            return CompetitorPage(
                url=url,
                status=ScrapeStatus.BLOCKED_BY_ROBOTS,
                quality_ok=False,
                notes=["disallowed by robots.txt"],
            )

        self._respect_rate_limit(url)
        try:
            resp = self._client.get(url)
        except httpx.HTTPError as exc:
            return CompetitorPage(
                url=url,
                status=ScrapeStatus.ERROR,
                quality_ok=False,
                notes=[f"request failed: {exc}"],
            )

        if resp.status_code >= 400:
            return CompetitorPage(
                url=url,
                status=ScrapeStatus.HTTP_ERROR,
                quality_ok=False,
                notes=[f"HTTP {resp.status_code}"],
            )

        final_url = str(resp.url)
        title, text, links = clean_html(resp.text, final_url)
        word_count = len(text.split())
        page = CompetitorPage(
            url=url,
            final_url=final_url,
            title=title,
            text=text,
            links=links,
            word_count=word_count,
        )
        quality_ok, reasons = assess_content(page, self.config.min_content_words)
        page.quality_ok = quality_ok
        page.status = ScrapeStatus.OK if quality_ok else ScrapeStatus.LOW_QUALITY
        page.notes = reasons

        self.cache.set(url, page.model_dump(mode="json"))
        return page

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Scraper:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
