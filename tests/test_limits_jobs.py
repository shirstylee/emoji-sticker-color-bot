from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.models.job import JobStatus
from app.models.limits import LimitsConfig
from app.services.jobs import ActiveJobError, JobManager
from app.services.user_rate_limiter import JobWeight, RateLimitExceeded, UserRateLimiter


@pytest.mark.asyncio
async def test_rolling_windows_and_admin_bypass() -> None:
    limiter = UserRateLimiter(LimitsConfig(jobs_10_minutes=2, jobs_hour=10, jobs_day=10))
    await limiter.check_and_record(1001, is_admin=False, now=0)
    await limiter.check_and_record(1001, is_admin=False, now=1)
    with pytest.raises(RateLimitExceeded):
        await limiter.check_and_record(1001, is_admin=False, now=2)
    await limiter.check_and_record(1001, is_admin=False, now=601)
    for _ in range(50):
        await limiter.check_and_record(1001, is_admin=True, weight=JobWeight(True, True, True))


@pytest.mark.asyncio
async def test_large_and_heavy_windows() -> None:
    limits = LimitsConfig(
        jobs_10_minutes=20,
        jobs_hour=20,
        jobs_day=20,
        large_hour=1,
        large_day=5,
        heavy_webm_hour=1,
        heavy_webm_day=5,
    )
    limiter = UserRateLimiter(limits)
    await limiter.check_and_record(42, is_admin=False, weight=JobWeight(large=True), now=0)
    with pytest.raises(RateLimitExceeded, match="large_1h"):
        await limiter.check_and_record(42, is_admin=False, weight=JobWeight(large=True), now=1)
    await limiter.check_and_record(43, is_admin=False, weight=JobWeight(heavy_webm=True), now=0)
    with pytest.raises(RateLimitExceeded, match="webm_1h"):
        await limiter.check_and_record(43, is_admin=False, weight=JobWeight(heavy_webm=True), now=1)


@pytest.mark.asyncio
async def test_one_regular_job_multiple_admin_jobs_and_cleanup(tmp_path: Path) -> None:
    manager = JobManager(tmp_path / "jobs")
    await manager.startup_cleanup()
    regular = await manager.create(user_id=1, chat_id=1, language="en", is_admin=False)
    with pytest.raises(ActiveJobError):
        await manager.create(user_id=1, chat_id=1, language="en", is_admin=False)
    first_admin = await manager.create(user_id=2, chat_id=2, language="en", is_admin=True)
    second_admin = await manager.create(user_id=2, chat_id=2, language="en", is_admin=True)
    assert manager.active_count == 3
    await manager.finish(regular.job_id)
    assert not regular.root.exists()
    await manager.cancel(first_admin.job_id)
    assert not first_admin.root.exists()
    await manager.finish(second_admin.job_id, JobStatus.FAILED)
    assert not second_admin.root.exists()


@pytest.mark.asyncio
async def test_timeout_cleanup(tmp_path: Path) -> None:
    manager = JobManager(tmp_path / "jobs", idle_timeout_seconds=10)
    await manager.startup_cleanup()
    job = await manager.create(user_id=1, chat_id=1, language="en", is_admin=False)
    job.status = JobStatus.AWAITING_COLOR
    job.last_interaction_at = datetime.now(UTC) - timedelta(seconds=11)
    expired = await manager.expire_idle(datetime.now(UTC))
    assert expired == 1
    assert manager.get(job.job_id) is None
    assert not job.root.exists()

