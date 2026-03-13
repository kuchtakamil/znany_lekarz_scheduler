from __future__ import annotations

import asyncio
import time


class RateLimiter:
    """Token bucket rate limiter - max N requests per minute."""

    def __init__(self, max_per_minute: int = 2) -> None:
        self._max_per_minute = max_per_minute
        self._interval = 60.0 / max_per_minute
        self._last_call: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self._interval:
                await asyncio.sleep(self._interval - elapsed)
            self._last_call = time.monotonic()
