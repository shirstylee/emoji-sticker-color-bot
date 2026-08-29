"""Format-aware processing pipeline with bounded, item-by-item memory use."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.config import Settings
from app.constants import (
    TELEGRAM_CUSTOM_EMOJI_SIDE,
    TELEGRAM_REGULAR_STICKER_SIDE,
    TELEGRAM_STATIC_STICKER_MAX_BYTES,
    TELEGRAM_TGS_MAX_BYTES,
    TELEGRAM_WEBM_MAX_BYTES,
)
from app.models.job import OutputType, RuntimeJob
from app.models.source import MediaFormat, SourceItem
from app.recolor.color_math import parse_color
from app.recolor.raster import recolor_raster_file
from app.recolor.tgs import recolor_tgs_file
from app.recolor.tgs_webm import render_tgs_webm
from app.recolor.webm import optimize_webm
from app.services.scheduler import JobScheduler, WorkKind
from app.validators.output import validate_processed_output

ProgressCallback = Callable[[int, int], Awaitable[None]]


def output_extension(item: SourceItem, output_type: OutputType) -> str:
    if output_type in {OutputType.EMOJI_PACK, OutputType.STICKER_PACK} and item.format in {
        MediaFormat.PNG,
        MediaFormat.WEBP,
    }:
        return ".webp"
    return f".{item.format.value}"


class ProcessingPipeline:
    def __init__(self, settings: Settings, scheduler: JobScheduler) -> None:
        self.settings = settings
        self.scheduler = scheduler

    async def prepare_chat_sticker(
        self,
        job: RuntimeJob,
        path: Path,
        media_format: MediaFormat,
    ) -> tuple[Path, MediaFormat]:
        """Prepare a native sendSticker asset while retaining the processed source file."""

        if media_format != MediaFormat.TGS:
            return path, media_format
        destination = job.root / "delivery" / f"{path.parent.name}_{path.stem}_chat.webm"

        async def render_operation() -> Path:
            return await render_tgs_webm(
                path,
                destination,
                side=TELEGRAM_REGULAR_STICKER_SIDE,
                maximum_bytes=TELEGRAM_WEBM_MAX_BYTES,
                cancel_event=job.cancel_event,
                timeout=self.settings.ffmpeg_timeout_seconds,
            )

        result = await self.scheduler.submit(
            WorkKind.WEBM,
            render_operation,
            is_admin=job.is_admin,
            heavy=True,
        )
        await validate_processed_output(
            result,
            expected=MediaFormat.WEBM,
            pack_custom=False,
            max_tgs_decompressed=self.settings.max_tgs_json,
        )
        return result, MediaFormat.WEBM

    async def process_item(
        self,
        job: RuntimeJob,
        item: SourceItem,
        *,
        preview: bool = False,
    ) -> Path:
        target = parse_color(job.selected_color or "#000000")
        adaptive = bool(getattr(job, "adaptive", False))
        strong = bool(item.needs_repainting and not adaptive)
        output_type = job.output_type or OutputType.FILE
        directory = job.root / ("preview" if preview else "processed")
        destination = directory / f"{item.index:03d}{output_extension(item, output_type)}"
        custom_emoji = output_type == OutputType.EMOJI_PACK
        pack_custom = (
            custom_emoji
            if output_type in {OutputType.EMOJI_PACK, OutputType.STICKER_PACK}
            else None
        )
        # Telegram thumbnails are often JPEG and therefore have no alpha. They
        # are useful for ordinary TGS previews, but must never be used to build
        # an Adaptive mask or a strong tint because their opaque background
        # would become part of the emoji.
        if preview and item.preview_path is not None and not adaptive and not strong:
            preview_source = item.preview_path
            destination = directory / f"{item.index:03d}.png"

            async def thumbnail_operation() -> Path:
                return await asyncio.to_thread(
                    recolor_raster_file,
                    preview_source,
                    destination,
                    target,
                    custom_emoji=None,
                    max_dimension=self.settings.max_raster_dimension,
                    max_pixels=self.settings.max_raster_pixels,
                    adaptive=adaptive,
                    strong=strong,
                )

            result = await self.scheduler.submit(
                WorkKind.PREVIEW,
                thumbnail_operation,
                is_admin=job.is_admin,
            )
            await validate_processed_output(
                result,
                expected=MediaFormat.PNG,
                pack_custom=None,
                max_tgs_decompressed=self.settings.max_tgs_json,
            )
            return result
        if item.format == MediaFormat.TGS:

            async def tgs_operation() -> Path:
                result = await asyncio.to_thread(
                    recolor_tgs_file,
                    item.path,
                    destination,
                    target,
                    max_decompressed=self.settings.max_tgs_json,
                    adaptive=adaptive,
                    strong=strong,
                )
                if result.stat().st_size > TELEGRAM_TGS_MAX_BYTES:
                    result.unlink(missing_ok=True)
                    raise ValueError("TGS exceeds Telegram's compact-file limit")
                return result

            result = await self.scheduler.submit(
                WorkKind.PREVIEW if preview else WorkKind.TGS,
                tgs_operation,
                is_admin=job.is_admin,
            )
            await validate_processed_output(
                result,
                expected=MediaFormat.TGS,
                pack_custom=pack_custom,
                max_tgs_decompressed=self.settings.max_tgs_json,
            )
            return result
        if item.format == MediaFormat.WEBM:
            side = (
                TELEGRAM_CUSTOM_EMOJI_SIDE
                if custom_emoji and not preview
                else TELEGRAM_REGULAR_STICKER_SIDE
            )

            async def webm_operation() -> Path:
                return await optimize_webm(
                    item.path,
                    destination,
                    target,
                    side=side,
                    maximum_bytes=TELEGRAM_WEBM_MAX_BYTES,
                    cancel_event=job.cancel_event,
                    timeout=self.settings.ffmpeg_timeout_seconds,
                    adaptive=adaptive,
                    strong=strong,
                )

            result = await self.scheduler.submit(
                WorkKind.WEBM,
                webm_operation,
                is_admin=job.is_admin,
                heavy=True,
            )
            await validate_processed_output(
                result,
                expected=MediaFormat.WEBM,
                pack_custom=None if preview else pack_custom,
                max_tgs_decompressed=self.settings.max_tgs_json,
            )
            return result

        if preview:
            # A raster preview is a chat photo, not a Telegram sticker asset.
            # Keeping it as PNG avoids WEBP sticker-dimension/type rejection.
            destination = directory / f"{item.index:03d}.png"

        async def raster_operation() -> Path:
            return await asyncio.to_thread(
                recolor_raster_file,
                item.path,
                destination,
                target,
                custom_emoji=custom_emoji
                if output_type in {OutputType.EMOJI_PACK, OutputType.STICKER_PACK}
                else None,
                max_dimension=self.settings.max_raster_dimension,
                max_pixels=self.settings.max_raster_pixels,
                maximum_bytes=TELEGRAM_STATIC_STICKER_MAX_BYTES
                if output_type in {OutputType.EMOJI_PACK, OutputType.STICKER_PACK}
                else None,
                adaptive=adaptive,
                strong=strong,
            )

        result = await self.scheduler.submit(
            WorkKind.PREVIEW if preview else WorkKind.RASTER,
            raster_operation,
            is_admin=job.is_admin,
        )
        await validate_processed_output(
            result,
            expected=MediaFormat.PNG if preview else item.format,
            pack_custom=None if preview else pack_custom,
            max_tgs_decompressed=self.settings.max_tgs_json,
        )
        return result

    async def process_all(
        self, job: RuntimeJob, progress: ProgressCallback | None = None
    ) -> list[tuple[SourceItem, Path]]:
        if job.source is None:
            raise RuntimeError("Job has no source")
        output: list[tuple[SourceItem, Path]] = []
        job.total = max(job.total, len(job.source.items) + len(job.errors))
        for item in job.source.items:
            if job.cancel_event.is_set():
                raise asyncio.CancelledError
            error: Exception | None = None
            path: Path | None = None
            for _ in range(2):
                try:
                    path = await self.process_item(job, item)
                    error = None
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as current_error:
                    error = current_error
            if path is None or error is not None:
                reason = str(error).strip() if error else "Processing failed"
                if not reason:
                    reason = type(error).__name__ if error else "Processing failed"
                job.errors.append((item.index, reason))
                continue
            output.append((item, path))
            job.progress = len(output)
            if progress:
                await progress(job.progress, job.total)
        if not output:
            raise RuntimeError("No source items could be processed")
        return output
