"""In-process sliding-window rate limits (one service process, so no shared store is needed)."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable


class RateLimiter:
    def __init__(
        self, limit: int, window_seconds: float = 60.0, clock: Callable[[], float] | None = None
    ) -> None:
        self.limit = limit
        self.window = window_seconds
        self.clock = clock or time.monotonic
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, float]:
        """Record a hit; returns (allowed, seconds until the next hit would be allowed)."""
        if self.limit <= 0:
            return True, 0.0
        now = self.clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False, max(0.0, hits[0] + self.window - now)
            hits.append(now)
            if len(self._hits) > 50_000:  # bound memory under key churn
                for k in [k for k, v in self._hits.items() if not v][:10_000]:
                    del self._hits[k]
            return True, 0.0
