"""
rate_limit.py - lightweight in-memory rate limiting helpers
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock


class SlidingWindowRateLimiter:
    def __init__(self):
        self._events = defaultdict(deque)
        self._lock = Lock()

    def hit(self, key, limit, window_seconds):
        now = time.monotonic()
        window_start = now - window_seconds

        with self._lock:
            events = self._events[key]
            while events and events[0] < window_start:
                events.popleft()

            if len(events) >= limit:
                retry_after = max(1, int(window_seconds - (now - events[0])))
                return False, retry_after

            events.append(now)
            return True, 0

    def reset(self):
        with self._lock:
            self._events.clear()


rate_limiter = SlidingWindowRateLimiter()
