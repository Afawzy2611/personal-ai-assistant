"""Simple in-memory per-API-key rate limiter.

For multi-instance / production scale, replace with Redis (or equivalent).
Documented in README as the next hardening step.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, Request, status

from config.settings import get_settings


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key_id: str, limit_per_minute: int) -> None:
        now = time.monotonic()
        window = 60.0
        with self._lock:
            q = self._hits[key_id]
            while q and (now - q[0]) > window:
                q.popleft()
            if len(q) >= limit_per_minute:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Try again later.",
                )
            q.append(now)


_limiter = InMemoryRateLimiter()


async def enforce_rate_limit(request: Request) -> None:
    cfg = get_settings()
    key_id = getattr(request.state, "api_key_id", None) or "anonymous"
    _limiter.check(key_id, cfg.rate_limit_per_minute)


def reset_rate_limiter_for_tests() -> None:
    """Test helper to clear counters between cases."""
    with _limiter._lock:
        _limiter._hits.clear()
