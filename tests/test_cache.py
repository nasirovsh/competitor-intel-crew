from __future__ import annotations

import time
from pathlib import Path

from competitor_intel.cache import DiskCache


def test_set_and_get_roundtrip(tmp_path: Path):
    cache = DiskCache(tmp_path, ttl_seconds=3600)
    cache.set("https://x.test", {"hello": "world"})
    assert cache.get("https://x.test") == {"hello": "world"}


def test_missing_key_returns_none(tmp_path: Path):
    cache = DiskCache(tmp_path)
    assert cache.get("https://nope.test") is None


def test_ttl_expiry(tmp_path: Path, monkeypatch):
    cache = DiskCache(tmp_path, ttl_seconds=10)
    cache.set("k", {"a": 1})
    # Simulate 20 seconds passing.
    real_time = time.time()
    monkeypatch.setattr(time, "time", lambda: real_time + 20)
    assert cache.get("k") is None


def test_disabled_cache_is_noop(tmp_path: Path):
    cache = DiskCache(tmp_path, enabled=False)
    cache.set("k", {"a": 1})
    assert cache.get("k") is None


def test_clear(tmp_path: Path):
    cache = DiskCache(tmp_path)
    cache.set("a", {"x": 1})
    cache.set("b", {"y": 2})
    cache.clear()
    assert cache.get("a") is None
    assert cache.get("b") is None
