"""A tiny in-memory sliding-window rate limiter for the public auth forms.

State is per process, so with N gunicorn workers the effective limit is up to
N times higher — good enough to blunt password guessing and sign-up spam
without adding Redis or another dependency.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: float, now: float | None = None) -> bool:
        """Record one attempt for ``key``; False if it exceeds ``limit`` per ``window`` seconds."""
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - window:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()
