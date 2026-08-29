"""RAM-only job manager and temporary-directory lifecycle."""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from app.models.job import JobStatus, RuntimeJob


class ActiveJobError(RuntimeError):
    """A regular user already has an active logical job."""


class JobManager:
    def __init__(self, temp_root: Path, idle_timeout_seconds: int = 900) -> None:
        self.temp_root = temp_root.resolve()
        self.idle_timeout_seconds = idle_timeout_seconds
        self._jobs: dict[str, RuntimeJob] = {}
        self._by_user: dict[int, set[str]] = {}
        self._deny_set: set[int] = set()
        self._lock = asyncio.Lock()
        self._sweeper: asyncio.Task[None] | None = None
        self._timeout_callback: Callable[[RuntimeJob], Awaitable[None]] | None = None
        self._timeout_notices: dict[int, datetime] = {}

    async def startup_cleanup(self) -> None:
        self._verify_temp_root()
        if self.temp_root.exists():
            for child in self.temp_root.iterdir():
                if child.is_dir() and child.parent == self.temp_root:
                    await asyncio.to_thread(shutil.rmtree, child, True)
                elif child.is_file() and child.parent == self.temp_root:
                    child.unlink(missing_ok=True)
        self.temp_root.mkdir(parents=True, exist_ok=True)

    def _verify_temp_root(self) -> None:
        if len(self.temp_root.parts) < 3 or self.temp_root == Path(self.temp_root.anchor):
            raise RuntimeError("TEMP_ROOT is dangerously broad")

    async def create(
        self, *, user_id: int, chat_id: int, language: str, is_admin: bool
    ) -> RuntimeJob:
        async with self._lock:
            if user_id in self._deny_set and not is_admin:
                raise PermissionError("Runtime access is temporarily restricted")
            active = self._by_user.get(user_id, set())
            if active and not is_admin:
                raise ActiveJobError("A regular user can have only one active job")
            job_id = uuid.uuid4().hex
            root = self.temp_root / job_id
            for name in ("source", "preview", "processed", "output"):
                (root / name).mkdir(parents=True, exist_ok=False)
            job = RuntimeJob(
                job_id=job_id,
                user_id=user_id,
                chat_id=chat_id,
                language=language,
                root=root,
                is_admin=is_admin,
            )
            self._jobs[job_id] = job
            self._by_user.setdefault(user_id, set()).add(job_id)
            return job

    def get(self, job_id: str) -> RuntimeJob | None:
        return self._jobs.get(job_id)

    def for_user(self, user_id: int) -> list[RuntimeJob]:
        return [self._jobs[item] for item in self._by_user.get(user_id, set()) if item in self._jobs]

    def owned(self, job_id: str, user_id: int, *, administrator: bool = False) -> RuntimeJob | None:
        job = self.get(job_id)
        return job if job and (job.user_id == user_id or administrator) else None

    async def finish(self, job_id: str, status: JobStatus = JobStatus.COMPLETED) -> None:
        async with self._lock:
            job = self._jobs.pop(job_id, None)
            if job is None:
                return
            job.status = status
            user_jobs = self._by_user.get(job.user_id)
            if user_jobs is not None:
                user_jobs.discard(job_id)
                if not user_jobs:
                    self._by_user.pop(job.user_id, None)
        await asyncio.to_thread(shutil.rmtree, job.root, True)

    async def cancel(self, job_id: str) -> RuntimeJob | None:
        job = self.get(job_id)
        if job is None:
            return None
        job.request_cancel()
        current = asyncio.current_task()
        if job.processing_task is not None and job.processing_task is not current:
            await asyncio.gather(job.processing_task, return_exceptions=True)
        await self.finish(job_id, JobStatus.CANCELLED)
        return job

    def temporarily_restrict(self, job_id: str) -> None:
        job = self.get(job_id)
        if job is not None and not job.is_admin:
            self._deny_set.add(job.user_id)

    def active_jobs(self) -> list[RuntimeJob]:
        return list(self._jobs.values())

    @property
    def active_count(self) -> int:
        return len(self._jobs)

    def start_sweeper(
        self, timeout_callback: Callable[[RuntimeJob], Awaitable[None]] | None = None
    ) -> None:
        self._timeout_callback = timeout_callback
        if self._sweeper is None or self._sweeper.done():
            self._sweeper = asyncio.create_task(self._sweep_loop(), name="job-idle-sweeper")

    async def _sweep_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(min(60, max(5, self.idle_timeout_seconds // 4)))
                await self.expire_idle()
        except asyncio.CancelledError:
            return

    async def expire_idle(self, now: datetime | None = None) -> int:
        current = now or datetime.now(UTC)
        expired = [
            job
            for job in self.active_jobs()
            if job.interactive
            and (current - job.last_interaction_at).total_seconds() >= self.idle_timeout_seconds
        ]
        notifications: dict[int, RuntimeJob] = {}
        notice_cooldown = max(300, self.idle_timeout_seconds)
        self._timeout_notices = {
            chat_id: timestamp
            for chat_id, timestamp in self._timeout_notices.items()
            if (current - timestamp).total_seconds() < notice_cooldown
        }
        for job in expired:
            last_notice = self._timeout_notices.get(job.chat_id)
            may_notify = last_notice is None or (
                current - last_notice
            ).total_seconds() >= notice_cooldown
            if job.notify_on_timeout and may_notify:
                notifications.setdefault(job.chat_id, job)
        # Remove every expired job first. A slow or failed Telegram notification
        # must never leave it active for the next sweep and send the same notice
        # again. Multiple admin jobs in one chat produce at most one notice.
        for job in expired:
            await self.cancel(job.job_id)
        if self._timeout_callback:
            for chat_id, job in notifications.items():
                self._timeout_notices[chat_id] = current
                with contextlib.suppress(Exception):
                    await self._timeout_callback(job)
        return len(expired)

    async def shutdown(self) -> None:
        if self._sweeper:
            self._sweeper.cancel()
            await asyncio.gather(self._sweeper, return_exceptions=True)
        for job in self.active_jobs():
            job.request_cancel()
        tasks = [
            job.processing_task
            for job in self.active_jobs()
            if job.processing_task is not None and not job.processing_task.done()
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for job_id in list(self._jobs):
            await self.finish(job_id, JobStatus.CANCELLED)
