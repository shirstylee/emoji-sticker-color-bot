"""Debounced, RAM-only media group collector."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from aiogram.types import Message


class MediaGroupCollector:
    def __init__(self, debounce_seconds: float = 0.8) -> None:
        self.debounce_seconds = debounce_seconds
        self._messages: dict[tuple[int, str], list[Message]] = {}
        self._tasks: dict[tuple[int, str], asyncio.Task[None]] = {}

    def add(
        self,
        user_id: int,
        group_id: str,
        message: Message,
        callback: Callable[[list[Message]], Awaitable[None]],
    ) -> None:
        key = (user_id, group_id)
        self._messages.setdefault(key, []).append(message)
        task = self._tasks.get(key)
        if task and not task.done():
            task.cancel()
        self._tasks[key] = asyncio.create_task(self._deliver(key, callback))

    async def _deliver(
        self,
        key: tuple[int, str],
        callback: Callable[[list[Message]], Awaitable[None]],
    ) -> None:
        try:
            await asyncio.sleep(self.debounce_seconds)
            messages = self._messages.pop(key, [])
            self._tasks.pop(key, None)
            if messages:
                await callback(messages)
        except asyncio.CancelledError:
            return

    async def shutdown(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        self._messages.clear()

