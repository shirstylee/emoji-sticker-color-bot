"""Aggregate-statistics helpers."""

from __future__ import annotations

from app.database.connection import Database


async def record_job_result(
    database: Database,
    *,
    success: bool,
    processed: int,
    tgs: int = 0,
    webm: int = 0,
    raster: int = 0,
    processing_ms: int = 0,
) -> None:
    await database.increment_statistics(
        {
            "jobs_total": 1,
            "jobs_success" if success else "jobs_failed": 1,
            "items_processed": processed,
            "tgs_processed": tgs,
            "webm_processed": webm,
            "raster_processed": raster,
            "processing_ms_total": processing_ms,
        }
    )

