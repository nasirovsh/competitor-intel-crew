"""Runtime configuration, loaded from environment variables / .env.

The LLM provider is fully env-configurable. By default we target a current
Anthropic Claude model; setting ``LLM_PROVIDER=openai`` (and an OpenAI key)
switches providers without code changes. Secrets are never committed - see
``.env.example`` for the full list of knobs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # optional dependency; .env loading is a convenience, not a requirement
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - exercised only when dotenv is absent

    def load_dotenv(*_args: object, **_kwargs: object) -> bool:
        return False


# Approximate list prices in USD per 1M tokens (input, output). Best-effort and
# configurable; used only for the per-run cost estimate surfaced in the report.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-opus-4-5": (5.0, 25.0),
    "claude-3-5-sonnet": (3.0, 15.0),
    "claude-3-5-haiku": (0.8, 4.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.4, 1.6),
}

DEFAULT_MODEL = "claude-sonnet-4-5"


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


@dataclass
class Config:
    """Resolved configuration for a single process."""

    # LLM
    provider: str = "anthropic"
    model: str = DEFAULT_MODEL
    temperature: float = 0.2
    api_key: str | None = None

    # Scraping
    user_agent: str = (
        "competitor-intel-crew/0.1 (+https://github.com/nasirovsh/competitor-intel-crew)"
    )
    request_timeout: float = 20.0
    requests_per_second: float = 1.0
    respect_robots: bool = True
    max_links_followed: int = 1

    # Cache
    cache_dir: Path = field(default_factory=lambda: Path(".cache/scrape"))
    cache_ttl_seconds: int = 24 * 60 * 60
    cache_enabled: bool = True

    # Quality / decision thresholds
    min_content_words: int = 120
    max_scrape_attempts: int = 2
    faithfulness_threshold: float = 0.7
    max_revision_attempts: int = 2

    # Output
    verbose: bool = False

    @property
    def model_string(self) -> str:
        """Provider-qualified model string for CrewAI's LLM factory."""
        if "/" in self.model:
            return self.model
        return f"{self.provider}/{self.model}"

    @property
    def bare_model(self) -> str:
        """Model id without any provider prefix (for pricing lookups)."""
        return self.model.split("/", 1)[-1]

    def pricing(self) -> tuple[float, float]:
        """(input, output) price per 1M tokens for the configured model."""
        bare = self.bare_model
        if bare in MODEL_PRICING:
            return MODEL_PRICING[bare]
        for known, price in MODEL_PRICING.items():
            if bare.startswith(known):
                return price
        return (0.0, 0.0)


def load_config(load_env: bool = True) -> Config:
    """Build a :class:`Config` from the environment (and ``.env`` if present)."""
    if load_env:
        load_dotenv()

    provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
    model = os.getenv("LLM_MODEL", "").strip() or _default_model_for(provider)

    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
        else:
            api_key = os.getenv("ANTHROPIC_API_KEY")

    cache_dir = Path(os.getenv("SCRAPE_CACHE_DIR", ".cache/scrape"))

    return Config(
        provider=provider,
        model=model,
        temperature=_get_float("LLM_TEMPERATURE", 0.2),
        api_key=api_key,
        user_agent=os.getenv("SCRAPER_USER_AGENT", Config.user_agent),
        request_timeout=_get_float("SCRAPER_TIMEOUT", 20.0),
        requests_per_second=_get_float("SCRAPER_RPS", 1.0),
        respect_robots=_get_bool("SCRAPER_RESPECT_ROBOTS", True),
        max_links_followed=_get_int("SCRAPER_MAX_LINKS", 1),
        cache_dir=cache_dir,
        cache_ttl_seconds=_get_int("SCRAPE_CACHE_TTL", 24 * 60 * 60),
        cache_enabled=_get_bool("SCRAPE_CACHE_ENABLED", True),
        min_content_words=_get_int("MIN_CONTENT_WORDS", 120),
        max_scrape_attempts=_get_int("MAX_SCRAPE_ATTEMPTS", 2),
        faithfulness_threshold=_get_float("FAITHFULNESS_THRESHOLD", 0.7),
        max_revision_attempts=_get_int("MAX_REVISION_ATTEMPTS", 2),
        verbose=_get_bool("CIC_VERBOSE", False),
    )


def _default_model_for(provider: str) -> str:
    if provider == "openai":
        return "gpt-4o-mini"
    return DEFAULT_MODEL
