"""RAM-only rolling-window limits with administrator bypass."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from app.models.limits import LimitsConfig


@dataclass(frozen=True, slots=True)
class JobWeight:
    large: bool = False
    very_large: bool = False
    heavy_webm: bool = False


def classify_job(*, items: int, extracted_bytes: int = 0, webm_items: int = 0) -> JobWeight:
    return JobWeight(
        large=items > 50 or extracted_bytes > 25 * 1024 * 1024,
        very_large=items > 120 or extracted_bytes > 75 * 1024 * 1024,
        heavy_webm=webm_items >= 10,
    )


class RateLimitExceeded(RuntimeError):
    """A RAM-only regular-user rolling window has been exhausted."""


class UserRateLimiter:
    def __init__(self, limits: LimitsConfig) -> None:
        self.limits = limits
        self._events: dict[int, dict[str, deque[float]]] = defaultdict(
            lambda: defaultdict(deque)
        )
        self._lock = asyncio.Lock()

    @staticmethod
    def _prune(events: deque[float], now: float, window: float) -> None:
        while events and now - events[0] >= window:
            events.popleft()

    async def check_and_record(
        self,
        user_id: int,
        *,
        is_admin: bool,
        weight: JobWeight | None = None,
        now: float | None = None,
    ) -> None:
        if is_admin:
            return
        weight = weight or JobWeight()
        current = time.monotonic() if now is None else now
        checks: list[tuple[str, float, int]] = [
            ("total_10m", 600, self.limits.jobs_10_minutes),
            ("total_1h", 3600, self.limits.jobs_hour),
            ("total_1d", 86400, self.limits.jobs_day),
        ]
        if weight.large:
            checks.extend(
                [("large_1h", 3600, self.limits.large_hour), ("large_1d", 86400, self.limits.large_day)]
            )
        if weight.very_large:
            checks.extend(
                [("huge_1h", 3600, self.limits.huge_hour), ("huge_1d", 86400, self.limits.huge_day)]
            )
        if weight.heavy_webm:
            checks.extend(
                [
                    ("webm_1h", 3600, self.limits.heavy_webm_hour),
                    ("webm_1d", 86400, self.limits.heavy_webm_day),
                ]
            )
        async with self._lock:
            user_events = self._events[user_id]
            for name, window, maximum in checks:
                self._prune(user_events[name], current, window)
                if len(user_events[name]) >= maximum:
                    raise RateLimitExceeded(name)
            for name, _, _ in checks:
                user_events[name].append(current)
