"""On-disk cache for scraped pages.

Development iterations should never re-hit competitor sites. Fetched pages are
stored as JSON keyed by a hash of the URL, with a TTL so stale entries expire.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


class DiskCache:
    """A tiny TTL'd JSON cache backed by files on disk."""

    def __init__(
        self, directory: Path | str, ttl_seconds: int = 86_400, enabled: bool = True
    ) -> None:
        self.directory = Path(directory)
        self.ttl_seconds = ttl_seconds
        self.enabled = enabled

    def _path_for(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        """Return the cached payload for ``key`` or ``None`` if missing/expired."""
        if not self.enabled:
            return None
        path = self._path_for(key)
        if not path.exists():
            return None
        try:
            envelope = json.loads(path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        stored_at = envelope.get("stored_at", 0)
        if self.ttl_seconds > 0 and (time.time() - stored_at) > self.ttl_seconds:
            return None
        return envelope.get("payload")

    def set(self, key: str, payload: dict[str, Any]) -> None:
        """Persist ``payload`` under ``key``."""
        if not self.enabled:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        envelope = {"key": key, "stored_at": time.time(), "payload": payload}
        tmp = self._path_for(key).with_suffix(".tmp")
        tmp.write_text(json.dumps(envelope), "utf-8")
        tmp.replace(self._path_for(key))

    def clear(self) -> None:
        """Delete every cached entry."""
        if not self.directory.exists():
            return
        for item in self.directory.glob("*.json"):
            item.unlink(missing_ok=True)
