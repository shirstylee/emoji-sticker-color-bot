"""Telegram sticker-call flood control driven by retry_after."""

from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def cancellation_aware_sleep(seconds: float, cancel_event: asyncio.Event) -> None:
    if seconds <= 0:
        return
    try:
        await asyncio.wait_for(cancel_event.wait(), timeout=seconds)
    except TimeoutError:
        return
    raise asyncio.CancelledError


class TelegramStickerRateController:
    def __init__(
        self,
        *,
        conservative_enabled: bool = False,
        conservative_requests: int = 8,
        conservative_window_seconds: int = 240,
        on_flood: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.enabled = conservative_enabled
        self.requests = max(1, conservative_requests)
        self.window = max(1, conservative_window_seconds)
        self.on_flood = on_flood
        self.last_retry_after: float | None = None
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def _conservative_wait(
        self,
        cancel_event: asyncio.Event,
        *,
        cost: int,
        on_wait: Callable[[float], Awaitable[None]] | None,
    ) -> None:
        if not self.enabled:
            return
        if cost <= 0:
            return
        if cost > self.requests:
            raise ValueError("Sticker operation cost exceeds the conservative window")
        while True:
            async with self._lock:
                now = time.monotonic()
                while self._timestamps and now - self._timestamps[0] >= self.window:
                    self._timestamps.popleft()
                if len(self._timestamps) + cost <= self.requests:
                    self._timestamps.extend([now] * cost)
                    return
                required_expirations = len(self._timestamps) + cost - self.requests
                deadline = self._timestamps[required_expirations - 1] + self.window
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                continue
            if on_wait:
                await on_wait(float(math.ceil(remaining)))
            await cancellation_aware_sleep(min(1.0, remaining), cancel_event)

    async def call(
        self,
        operation: Callable[[], Awaitable[T]],
        cancel_event: asyncio.Event,
        *,
        maximum_attempts: int = 8,
        on_flood: Callable[[float], Awaitable[None]] | None = None,
        conservative: bool = False,
        conservative_cost: int = 1,
    ) -> T:
        attempts = 0
        if conservative:
            # Reserve the logical mutation once. A retry_after retry is the
            # same operation and must not consume the local window a second
            # time after Telegram's own countdown has elapsed.
            await self._conservative_wait(
                cancel_event,
                cost=conservative_cost,
                on_wait=on_flood,
            )
        while True:
            if cancel_event.is_set():
                raise asyncio.CancelledError
            try:
                return await operation()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                retry_after = getattr(error, "retry_after", None)
                if retry_after is None:
                    raise
                attempts += 1
                if attempts >= maximum_attempts:
                    raise
                delay = max(0.0, float(retry_after))
                self.last_retry_after = delay
                if self.on_flood:
                    await self.on_flood(delay)
                deadline = time.monotonic() + delay
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    if on_flood:
                        await on_flood(float(math.ceil(remaining)))
                    await cancellation_aware_sleep(min(1.0, remaining), cancel_event)
