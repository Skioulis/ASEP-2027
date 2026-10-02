"""A tiny in-memory sliding-window rate limiter for the public auth forms.

State is per process, so with N gunicorn workers the effective limit is up to
N times higher — good enough to blunt password guessing and sign-up spam
without adding Redis or another dependency.

Keys are built from raw form input, so memory is bounded two ways: every key is
truncated to ``MAX_KEY_LENGTH`` characters (real usernames are at most 32, so
only junk input is affected), and every ``prune_every`` calls any key whose
newest hit has left the largest window seen so far is dropped.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

MAX_KEY_LENGTH = 128


class RateLimiter:
    def __init__(self, prune_every: int = 256) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._prune_every = max(1, prune_every)
        self._calls = 0
        self._max_window = 0.0

    def __len__(self) -> int:
        """Number of keys currently tracked."""
        with self._lock:
            return len(self._hits)

    def hit(self, key: str, limit: int, window: float, now: float | None = None) -> bool:
        """Record one attempt for ``key``; False if it exceeds ``limit`` per ``window`` seconds."""
        now = time.monotonic() if now is None else now
        key = key[:MAX_KEY_LENGTH]
        with self._lock:
            self._max_window = max(self._max_window, window)
            self._calls += 1
            if self._calls % self._prune_every == 0:
                self._prune(now)
            hits = self._hits[key]
            while hits and hits[0] <= now - window:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def _prune(self, now: float) -> None:
        """Drop keys with no hit inside the largest window (caller holds the lock)."""
        cutoff = now - self._max_window
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= cutoff]:
            del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()
