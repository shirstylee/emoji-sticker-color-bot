"""Priority scheduler with bounded workload-specific concurrency and safety checks."""

from __future__ import annotations

import asyncio
import itertools
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Generic, TypeVar

import psutil

T = TypeVar("T")


class WorkKind(StrEnum):
    TGS = "tgs"
    RASTER = "raster"
    WEBM = "webm"
    ARCHIVE = "archive"
    PREVIEW = "preview"


class SchedulerOverloaded(RuntimeError):
    """The bounded scheduler cannot accept another regular job."""


class ResourceUnsafe(RuntimeError):
    """Available server resources are below safe processing thresholds."""


@dataclass(order=True, slots=True)
class ScheduledWork(Generic[T]):
    priority: int
    sequence: int
    kind: WorkKind = field(compare=False)
    operation: Callable[[], Awaitable[T]] = field(compare=False)
    result: asyncio.Future[T] = field(compare=False)
    heavy: bool = field(compare=False, default=False)


class JobScheduler:
    def __init__(
        self,
        *,
        temp_root: Path,
        global_workers: int,
        tgs_workers: int,
        raster_workers: int,
        webm_workers: int,
        archive_workers: int,
        preview_workers: int,
        pending_regular: int,
        ram_min_mib: int,
        disk_min_mib: int,
    ) -> None:
        self.temp_root = temp_root
        self.pending_regular = pending_regular
        self.ram_min = ram_min_mib * 1024 * 1024
        self.disk_min = disk_min_mib * 1024 * 1024
        self.queue: asyncio.PriorityQueue[ScheduledWork[Any]] = asyncio.PriorityQueue()
        self.semaphores = {
            WorkKind.TGS: asyncio.Semaphore(tgs_workers),
            WorkKind.RASTER: asyncio.Semaphore(raster_workers),
            WorkKind.WEBM: asyncio.Semaphore(webm_workers),
            WorkKind.ARCHIVE: asyncio.Semaphore(archive_workers),
            WorkKind.PREVIEW: asyncio.Semaphore(preview_workers),
        }
        self.global_workers = global_workers
        self._workers: list[asyncio.Task[None]] = []
        self._sequence = itertools.count()
        self.accepting = True
        self.running = 0

    def start(self) -> None:
        if not self._workers:
            self._workers = [
                asyncio.create_task(self._worker(), name=f"scheduler-{index}")
                for index in range(self.global_workers)
            ]

    async def submit(
        self,
        kind: WorkKind,
        operation: Callable[[], Awaitable[T]],
        *,
        is_admin: bool,
        heavy: bool = False,
    ) -> T:
        if not self.accepting:
            raise SchedulerOverloaded("Scheduler is stopping")
        if not is_admin and self.queue.qsize() >= self.pending_regular:
            raise SchedulerOverloaded("Regular pending ceiling reached")
        loop = asyncio.get_running_loop()
        future: asyncio.Future[T] = loop.create_future()
        await self.queue.put(
            ScheduledWork(0 if is_admin else 10, next(self._sequence), kind, operation, future, heavy)
        )
        return await future

    async def _resource_wait(self, heavy: bool) -> None:
        if not heavy:
            return
        while True:
            memory = psutil.virtual_memory()
            disk = shutil.disk_usage(self.temp_root)
            if memory.available >= self.ram_min and memory.percent <= 90 and disk.free >= self.disk_min:
                return
            await asyncio.sleep(5)

    async def _worker(self) -> None:
        while True:
            work = await self.queue.get()
            if work.result.cancelled():
                self.queue.task_done()
                continue
            try:
                await self._resource_wait(work.heavy)
                async with self.semaphores[work.kind]:
                    self.running += 1
                    result = await work.operation()
                if not work.result.done():
                    work.result.set_result(result)
            except asyncio.CancelledError:
                if not work.result.done():
                    work.result.cancel()
                raise
            except BaseException as error:
                if not work.result.done():
                    work.result.set_exception(error)
            finally:
                self.running = max(0, self.running - 1)
                self.queue.task_done()

    async def shutdown(self) -> None:
        self.accepting = False
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        while not self.queue.empty():
            work = self.queue.get_nowait()
            if not work.result.done():
                work.result.cancel()
            self.queue.task_done()

    @property
    def pending(self) -> int:
        return self.queue.qsize()
