"""Private-chat source, color, preview, output, publishing and cleanup workflow."""

from __future__ import annotations

import asyncio
import contextlib
import html
import logging
import math
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import psutil
from aiogram import F, Router
from aiogram.enums import MessageEntityType
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.constants import TELEGRAM_CUSTOM_EMOJI_SET_MAX, TELEGRAM_REGULAR_STICKER_SET_MAX
from app.context import AppContext
from app.database.settings import maintenance_enabled
from app.database.statistics import record_job_result
from app.handlers.commands import current_language, show_main_menu
from app.i18n import text
from app.keyboards.user import (
    adaptive_preview_keyboard,
    color_keyboard,
    output_keyboard,
    pack_name_keyboard,
    preview_keyboard,
    processing_keyboard,
    result_keyboard,
    single_result_keyboard,
    split_keyboard,
)
from app.logging import safe_error
from app.models.job import JobStatus, OutputType, RuntimeJob
from app.models.source import MediaFormat, SourceItem, SourceKind
from app.recolor.color_math import parse_color
from app.services.archive import split_output_zip
from app.services.jobs import ActiveJobError
from app.services.source_resolver import (
    SourceError,
    message_pack_link,
    resolve_media_group,
    resolve_message,
)
from app.services.telegram_stickers import pack_url
from app.services.unicode_emoji import extract_single_emoji
from app.services.user_rate_limiter import RateLimitExceeded, classify_job
from app.validators.common import detect_format

LOGGER = logging.getLogger(__name__)
router = Router(name="workflow")


def _countdown(seconds: float) -> str:
    total = max(0, math.ceil(seconds))
    minutes, remainder = divmod(total, 60)
    return f"{minutes:02d}:{remainder:02d}"


async def _show_flood_wait(
    control: Message,
    job: RuntimeJob,
    context: AppContext,
    remaining: float,
    done: int | None = None,
    total: int | None = None,
    publishing: bool = False,
    prepared: int | None = None,
) -> None:
    try:
        await context.ui.edit(
            control,
            f'{context.premium.html("TIME")} '
            + text(
                job.language,
                "pack_flood_wait" if publishing else "flood_wait",
                seconds=_countdown(remaining),
                done=job.progress if done is None else done,
                total=job.total if total is None else total,
                prepared=job.progress if prepared is None else prepared,
                **context.premium.placeholders(),
            ),
            reply_markup=processing_keyboard(
                context.premium, job.job_id, job.language
            ),
        )
    except Exception:
        return


async def _telegram_send(
    operation: Callable[[], Awaitable[Message]],
    control: Message,
    job: RuntimeJob,
    context: AppContext,
) -> Message:
    return await context.telegram_limiter.call(
        operation,
        job.cancel_event,
        on_flood=lambda remaining: _show_flood_wait(
            control, job, context, remaining
        ),
    )


def _job_kind(job: RuntimeJob) -> str:
    if job.source is None:
        return "Источник" if job.language == "ru" else "Source"
    names = (
        {
            SourceKind.STICKER: "Стикер",
            SourceKind.CUSTOM_EMOJI: "Premium Emoji",
            SourceKind.PACK: "Telegram-набор",
            SourceKind.FILE: "Файл",
            SourceKind.ZIP: "ZIP-архив",
            SourceKind.UNICODE: "Unicode Emoji",
            SourceKind.MEDIA_GROUP: "Группа файлов",
        }
        if job.language == "ru"
        else {
            SourceKind.STICKER: "Sticker",
            SourceKind.CUSTOM_EMOJI: "Custom Emoji",
            SourceKind.PACK: "Telegram Pack",
            SourceKind.FILE: "File",
            SourceKind.ZIP: "ZIP",
            SourceKind.UNICODE: "Unicode Emoji",
            SourceKind.MEDIA_GROUP: "Media group",
        }
    )
    return names[job.source.kind]


def _format_summary(job: RuntimeJob) -> str:
    if job.source is None:
        return "—"
    return "\n".join(
        f"{media.value.upper()}: {count}" for media, count in job.source.format_counts.items()
    )


async def _send_source_card(message: Message, job: RuntimeJob, context: AppContext) -> None:
    if job.source is None:
        return
    title = html.escape(job.source.title or "—")
    body = text(
        job.language,
        "pack_source_found" if job.source.kind == SourceKind.PACK else "source_found",
        icon=context.premium.html("PACK"),
        title=title,
        kind=_job_kind(job),
        count=job.total,
        formats=_format_summary(job),
        **context.premium.placeholders(),
    )
    previous_menu = context.menu_messages.pop(job.user_id, None)
    if previous_menu is not None:
        with contextlib.suppress(Exception):
            await context.bot.delete_message(previous_menu[0], previous_menu[1])
    sent = await context.ui.answer(
        message,
        body,
        reply_markup=color_keyboard(
            context.premium,
            job.job_id,
            context.settings.color_picker_url,
            adaptive=True,
            language=job.language,
        ),
    )
    job.control_message_id = sent.message_id


async def _source_error(message: Message, language: str, context: AppContext, error: Exception) -> None:
    key = "service_error"
    name = type(error).__name__.lower()
    detail = str(error).lower()
    if "too large" in detail or ("limit" in detail and "duration" not in detail):
        key = "file_too_large"
    elif "archive" in name or "zip" in detail:
        key = "archive_invalid"
    elif "tgs" in name or "tgs" in detail:
        key = "tgs_invalid"
    elif "font" in detail:
        key = "emoji_font_missing"
    await context.ui.answer(
        message,
        f'{context.premium.html("ERROR")} {text(language, key)}',
    )


async def _accept_source(
    message: Message, context: AppContext, media_messages: list[Message] | None = None
) -> None:
    if message.from_user is None:
        return
    user_id = message.from_user.id
    is_admin = await context.admins.is_admin(user_id)
    language = current_language(message, context, is_admin=is_admin)
    if context.shutdown_requested:
        await context.ui.answer(
            message, f'{context.premium.html("WARNING")} {text(language, "overloaded")}'
        )
        return
    if not is_admin and await maintenance_enabled(context.database):
        await context.ui.answer(
            message, f'{context.premium.html("SETTINGS")} {text(language, "maintenance")}'
        )
        return
    if context.jobs.for_user(user_id) and not is_admin:
        await context.ui.answer(
            message, f'{context.premium.html("WARNING")} {text(language, "busy")}'
        )
        return
    if not is_admin and context.scheduler.pending >= context.settings.global_pending_regular:
        await context.ui.answer(
            message, f'{context.premium.html("WARNING")} {text(language, "overloaded")}'
        )
        return
    disk = psutil.disk_usage(str(context.settings.temp_root))
    if disk.free < context.settings.disk_safety_min_mib * 1024 * 1024 or disk.free / disk.total < 0.10:
        await context.ui.answer(
            message, f'{context.premium.html("WARNING")} {text(language, "overloaded")}'
        )
        return
    try:
        job = await context.jobs.create(
            user_id=user_id, chat_id=message.chat.id, language=language, is_admin=is_admin
        )
    except ActiveJobError:
        await context.ui.answer(
            message, f'{context.premium.html("WARNING")} {text(language, "busy")}'
        )
        return
    try:
        if media_messages is not None:
            source = await resolve_media_group(
                context.bot, job, media_messages, context.settings
            )
        else:
            source = await resolve_message(context.bot, job, message, context.settings)
        job.source = source
        extracted = sum(item.path.stat().st_size for item in source.items)
        webm = sum(item.format == MediaFormat.WEBM for item in source.items)
        await context.user_limiter.check_and_record(
            user_id,
            is_admin=is_admin,
            weight=classify_job(items=len(source.items), extracted_bytes=extracted, webm_items=webm),
        )
        job.status = JobStatus.AWAITING_COLOR
        job.total = len(source.items) + len(job.errors)
        await _send_source_card(message, job, context)
        for source_message in media_messages or [message]:
            with contextlib.suppress(Exception):
                await source_message.delete()
    except (SourceError, ValueError, OSError) as error:
        context.errors.add(job_id=job.job_id, component="source", error=error)
        safe_error(LOGGER, "source", error, job.job_id)
        await context.jobs.finish(job.job_id, JobStatus.FAILED)
        await _source_error(message, language, context, error)
    except RateLimitExceeded:
        await context.jobs.finish(job.job_id, JobStatus.CANCELLED)
        await context.ui.answer(
            message, f'{context.premium.html("TIME")} {text(language, "rate_limited")}'
        )
    except BaseException:
        await context.jobs.finish(job.job_id, JobStatus.FAILED)
        raise


def _looks_like_new_source(message: Message) -> bool:
    if message.sticker or message.document:
        return True
    value = (message.text or "").strip()
    return (
        message_pack_link(message) is not None
        or extract_single_emoji(value) is not None
        or any(
            entity.type == MessageEntityType.CUSTOM_EMOJI
            for entity in (message.entities or [])
        )
    )


@router.message(F.chat.type == "private")
async def private_message(message: Message, context: AppContext) -> None:
    if message.from_user is None:
        return
    is_admin = await context.admins.is_admin(message.from_user.id)
    active = sorted(context.jobs.for_user(message.from_user.id), key=lambda item: item.created_at)
    if active:
        job = active[-1]
        if job.status == JobStatus.AWAITING_COLOR and message.text and not _looks_like_new_source(message):
            await _handle_color_text(message, job, context)
            return
        if (
            job.status == JobStatus.AWAITING_PACK_NAME
            and message.text
            and not _looks_like_new_source(message)
        ):
            await _handle_pack_name(message, job, context)
            return
        if is_admin and _looks_like_new_source(message):
            if message.media_group_id:
                context.media_groups.add(
                    message.from_user.id,
                    message.media_group_id,
                    message,
                    lambda messages: _accept_source(messages[0], context, messages),
                )
            else:
                await _accept_source(message, context)
            return
        await context.ui.answer(
            message,
            f'{context.premium.html("WARNING")} {text(job.language, "busy")}',
            reply_markup=processing_keyboard(
                context.premium, job.job_id, job.language
            ),
        )
        return
    if message.media_group_id:
        context.media_groups.add(
            message.from_user.id,
            message.media_group_id,
            message,
            lambda messages: _accept_source(messages[0], context, messages),
        )
        return
    await _accept_source(message, context)


async def _delete_old_preview(job: RuntimeJob, context: AppContext) -> None:
    if job.preview_message_id is None:
        return
    with contextlib.suppress(Exception):
        await context.bot.delete_message(job.chat_id, job.preview_message_id)
    job.preview_message_id = None


async def _send_preview(
    control: Message, job: RuntimeJob, path: Path, media_format: MediaFormat, context: AppContext
) -> None:
    await _delete_old_preview(job, context)
    filename = f"preview{path.suffix.lower()}"
    if media_format == MediaFormat.PNG:
        preview = await _telegram_send(
            lambda: control.answer_photo(FSInputFile(path, filename=filename)),
            control,
            job,
            context,
        )
    else:
        preview = await context.publisher.send_sticker_file(
            user_id=job.user_id,
            chat_id=job.chat_id,
            path=path,
            media_format=media_format,
            cancel_event=job.cancel_event,
            on_flood=lambda remaining: _show_flood_wait(
                control, job, context, remaining
            ),
        )
    job.preview_message_id = preview.message_id


async def _select_color(
    control: Message, job: RuntimeJob, color_value: str, context: AppContext
) -> None:
    try:
        color = parse_color(color_value)
    except ValueError:
        await context.ui.answer(
            control,
            f'{context.premium.html("ERROR")} {text(job.language, "invalid_color")}',
        )
        return
    if not job.is_admin and job.color_changes >= context.limits.preview_color_changes:
        await context.ui.answer(
            control,
            f'{context.premium.html("TIME")} {text(job.language, "rate_limited")}',
        )
        return
    job.color_changes += 1
    job.selected_color = color.hex
    job.adaptive = False
    job.touch()
    if job.source is None:
        return
    if len(job.source.items) == 1:
        job.output_type = OutputType.STICKER_PACK
        job.status = JobStatus.PROCESSING
        task = asyncio.create_task(
            _run_single_result(control, job, context),
            name=f"single-{job.short_id}",
        )
        job.processing_task = task
        return
    job.status = JobStatus.GENERATING_PREVIEW
    preview_error: Exception | None = None
    for preview_item in job.source.items:
        try:
            path = await context.pipeline.process_item(job, preview_item, preview=True)
            preview_format = (
                MediaFormat.PNG if path.suffix.lower() == ".png" else preview_item.format
            )
            await _send_preview(control, job, path, preview_format, context)
            preview_error = None
            break
        except Exception as error:
            preview_error = error
    if preview_error is not None:
        context.errors.add(job_id=job.job_id, component="preview", error=preview_error)
        await _source_error(control, job.language, context, preview_error)
        job.status = JobStatus.AWAITING_COLOR
        return
    job.status = JobStatus.AWAITING_PREVIEW_DECISION
    await context.ui.edit(
        control,
        text(
            job.language,
            "preview_ready",
            icon=context.premium.html("PREVIEW"),
            **context.premium.placeholders(),
        ),
        reply_markup=preview_keyboard(context.premium, job.job_id, job.language),
    )


async def _handle_color_text(message: Message, job: RuntimeJob, context: AppContext) -> None:
    try:
        parse_color(message.text or "")
    except ValueError:
        await context.ui.answer(
            message,
            f'{context.premium.html("ERROR")} {text(job.language, "invalid_color")}',
        )
        return
    control: Message | None = None
    if job.control_message_id is not None:
        try:
            edited = await context.bot.edit_message_text(
                chat_id=job.chat_id,
                message_id=job.control_message_id,
                text=text(
                    job.language,
                    "processing",
                    icon=context.premium.html("LOADING"),
                    done=0,
                    total=max(1, job.total),
                ),
                reply_markup=processing_keyboard(
                    context.premium, job.job_id, job.language
                ),
            )
            if isinstance(edited, Message):
                control = edited
        except Exception:
            control = None
    if control is None:
        control = await context.ui.answer(
            message,
            text(
                job.language,
                "processing",
                icon=context.premium.html("LOADING"),
                done=0,
                total=max(1, job.total),
            ),
            reply_markup=processing_keyboard(context.premium, job.job_id, job.language),
        )
        job.control_message_id = control.message_id
    with contextlib.suppress(Exception):
        await message.delete()
    await _select_color(control, job, message.text or "", context)


async def _request_pack_name(control: Message, job: RuntimeJob, context: AppContext) -> None:
    job.status = JobStatus.AWAITING_PACK_NAME
    await context.ui.edit(
        control,
        f'{context.premium.html("EDIT")} {text(job.language, "enter_pack_name")}',
        reply_markup=pack_name_keyboard(
            context.premium,
            job.job_id,
            source_title=bool(job.source and job.source.kind == SourceKind.PACK and job.source.title),
            language=job.language,
        ),
    )


async def _handle_pack_name(message: Message, job: RuntimeJob, context: AppContext) -> None:
    title = (message.text or "").strip()
    if not 1 <= len(title) <= 64:
        await context.ui.answer(
            message,
            f'{context.premium.html("ERROR")} {text(job.language, "invalid_pack_name")}',
        )
        return
    job.pack_title = title
    control: Message | None = None
    if job.control_message_id is not None:
        try:
            edited = await context.bot.edit_message_text(
                chat_id=job.chat_id,
                message_id=job.control_message_id,
                text=text(
                    job.language,
                    "processing",
                    icon=context.premium.html("LOADING"),
                    done=0,
                    total=max(1, job.total),
                ),
                reply_markup=processing_keyboard(
                    context.premium, job.job_id, job.language
                ),
            )
            if isinstance(edited, Message):
                control = edited
        except Exception:
            control = None
    if control is None:
        control = await context.ui.answer(
            message,
            text(
                job.language,
                "processing",
                icon=context.premium.html("LOADING"),
                done=0,
                total=max(1, job.total),
            ),
            reply_markup=processing_keyboard(context.premium, job.job_id, job.language),
        )
        job.control_message_id = control.message_id
    with contextlib.suppress(Exception):
        await message.delete()
    await _start_processing(control, job, context)


async def _start_processing(control: Message, job: RuntimeJob, context: AppContext) -> None:
    if job.source is None or job.output_type is None:
        return
    if job.output_type in {OutputType.EMOJI_PACK, OutputType.STICKER_PACK}:
        maximum = (
            TELEGRAM_CUSTOM_EMOJI_SET_MAX
            if job.output_type == OutputType.EMOJI_PACK
            else TELEGRAM_REGULAR_STICKER_SET_MAX
        )
        if len(job.source.items) > maximum and not job.split_allowed:
            job.status = JobStatus.AWAITING_SPLIT_CONFIRMATION
            await context.ui.edit(
                control,
                f'{context.premium.html("PACK")} {text(job.language, "split_confirm")}',
                reply_markup=split_keyboard(context.premium, job.job_id, job.language),
            )
            return
    job.status = JobStatus.PROCESSING
    task = asyncio.create_task(_run_job(control, job, context), name=f"job-{job.short_id}")
    job.processing_task = task


async def _run_single_result(
    control: Message, job: RuntimeJob, context: AppContext
) -> None:
    started = time.monotonic()
    try:
        await context.ui.edit(
            control,
            text(
                job.language,
                "processing",
                icon=context.premium.html("LOADING"),
                done=0,
                total=1,
            ),
            reply_markup=processing_keyboard(
                context.premium, job.job_id, job.language
            ),
        )
        outputs = await context.pipeline.process_all(job)
        item, path = outputs[0]
        await context.publisher.send_sticker_file(
            user_id=job.user_id,
            chat_id=job.chat_id,
            path=path,
            media_format=detect_format(path),
            cancel_event=job.cancel_event,
            on_flood=lambda remaining: _show_flood_wait(
                control, job, context, remaining, done=1, total=1
            ),
        )
        job.status = JobStatus.AWAITING_RESULT_ACTION
        await context.ui.edit(
            control,
            text(
                job.language,
                "single_result_ready",
                icon=context.premium.html("SUCCESS"),
                color=job.selected_color or "Adaptive",
                **context.premium.placeholders(),
            ),
            reply_markup=single_result_keyboard(
                context.premium, job.job_id, job.language
            ),
        )
        if not job.statistics_recorded:
            await record_job_result(
                context.database,
                success=True,
                processed=1,
                tgs=int(item.format == MediaFormat.TGS),
                webm=int(item.format == MediaFormat.WEBM),
                raster=int(item.format in {MediaFormat.PNG, MediaFormat.WEBP}),
                processing_ms=round((time.monotonic() - started) * 1000),
            )
            job.statistics_recorded = True
    except asyncio.CancelledError:
        raise
    except Exception as error:
        context.errors.add(job_id=job.job_id, component="processing", error=error)
        safe_error(LOGGER, "processing", error, job.job_id)
        if not job.statistics_recorded:
            await record_job_result(
                context.database,
                success=False,
                processed=job.progress,
                processing_ms=round((time.monotonic() - started) * 1000),
            )
        with contextlib.suppress(Exception):
            await context.ui.edit(
                control,
                f'{context.premium.html("ERROR")} '
                + text(job.language, "service_error"),
            )
        await context.jobs.finish(job.job_id, JobStatus.FAILED)


async def _run_job(control: Message, job: RuntimeJob, context: AppContext) -> None:
    started = time.monotonic()
    last_progress = 0.0
    final_status = JobStatus.COMPLETED

    async def progress(done: int, total: int) -> None:
        nonlocal last_progress
        now = time.monotonic()
        if now - last_progress < 1.7 and done != total:
            return
        last_progress = now
        try:
            await context.ui.edit(
                control,
                text(
                    job.language,
                    "processing",
                    icon=context.premium.html("LOADING"),
                    done=done,
                    total=total,
                ),
                reply_markup=processing_keyboard(
                    context.premium, job.job_id, job.language
                ),
            )
        except Exception:
            return

    try:
        await progress(0, job.total)
        outputs = await context.pipeline.process_all(job, progress)
        if job.output_type == OutputType.FILE:
            path = outputs[0][1]
            await _telegram_send(
                lambda: control.answer_document(
                    FSInputFile(
                        path, filename=f"recolored{path.suffix.lower()}"
                    )
                ),
                control,
                job,
                context,
            )
            await context.ui.edit(
                control,
                text(
                    job.language,
                    "done_file",
                    icon=context.premium.html("SUCCESS"),
                    color=job.selected_color or "Adaptive",
                    **context.premium.placeholders(),
                ),
                reply_markup=result_keyboard(context.premium, language=job.language),
            )
        elif job.output_type == OutputType.ZIP:
            await _deliver_zip(control, job, [path for _, path in outputs], context)
        else:
            await _publish_packs(control, job, outputs, context)
        formats = [item.format for item, _ in outputs]
        if not job.statistics_recorded:
            await record_job_result(
                context.database,
                success=True,
                processed=len(outputs),
                tgs=formats.count(MediaFormat.TGS),
                webm=formats.count(MediaFormat.WEBM),
                raster=formats.count(MediaFormat.PNG) + formats.count(MediaFormat.WEBP),
                processing_ms=round((time.monotonic() - started) * 1000),
            )
            job.statistics_recorded = True
    except asyncio.CancelledError:
        final_status = JobStatus.CANCELLED
        if job.created_sets:
            await context.publisher.delete_sets(job.created_sets)
        raise
    except Exception as error:
        final_status = JobStatus.FAILED
        context.errors.add(job_id=job.job_id, component="processing", error=error)
        safe_error(LOGGER, "processing", error, job.job_id)
        if not job.statistics_recorded:
            await record_job_result(
                context.database,
                success=False,
                processed=job.progress,
                processing_ms=round((time.monotonic() - started) * 1000),
            )
        with contextlib.suppress(Exception):
            body = text(job.language, "service_error", icon=context.premium.html("ERROR"))
            if job.errors:
                body += "\n\n" + _error_summary(job)
            await context.ui.edit(
                control,
                body,
            )
    finally:
        await _delete_old_preview(job, context)
        await context.jobs.finish(job.job_id, final_status)


async def _deliver_zip(
    control: Message, job: RuntimeJob, files: list[Path], context: AppContext
) -> None:
    title = job.pack_title or (job.source.title if job.source else None) or "Recolored"
    parts = await asyncio.to_thread(
        split_output_zip,
        files,
        job.root / "output",
        pack_name=title,
        selected_color=job.selected_color or "Adaptive",
        mode="adaptive" if job.adaptive else "fixed color",
        part_limit=context.settings.max_output_zip_part,
    )
    for part in parts:
        async def send_part(part: Path = part) -> Message:
            return await control.answer_document(
                FSInputFile(part, filename=part.name)
            )

        await _telegram_send(
            send_part,
            control,
            job,
            context,
        )
    body = text(
        job.language,
        "done_file",
        icon=context.premium.html("SUCCESS"),
        color=job.selected_color or "Adaptive",
        **context.premium.placeholders(),
    )
    if job.errors:
        body += "\n\n" + _error_summary(job)
    await context.ui.edit(
        control,
        body,
        reply_markup=result_keyboard(context.premium, language=job.language),
    )


async def _publish_packs(
    control: Message,
    job: RuntimeJob,
    outputs: list[tuple[SourceItem, Path]],
    context: AppContext,
) -> None:
    if job.output_type is None:
        return
    custom = job.output_type == OutputType.EMOJI_PACK
    maximum = TELEGRAM_CUSTOM_EMOJI_SET_MAX if custom else TELEGRAM_REGULAR_STICKER_SET_MAX
    title = job.pack_title or "Recolored"
    job.status = JobStatus.PUBLISHING
    job.progress = 0
    job.total = len(outputs)
    await context.ui.edit(
        control,
        text(
            job.language,
            "publishing",
            icon=context.premium.html("UPLOAD"),
            prepared=0,
            done=0,
            total=len(outputs),
            **context.premium.placeholders(),
        ),
        reply_markup=processing_keyboard(context.premium, job.job_id, job.language),
    )
    groups = [outputs[index : index + maximum] for index in range(0, len(outputs), maximum)]
    links: list[str] = []
    saved_packs: list[dict[str, str]] = []
    published = 0
    prepared = 0
    last_publication_update = 0.0
    for index, group in enumerate(groups, 1):
        group_offset = published
        group_state = {
            "offset": group_offset,
            "prepared": prepared,
            "published": published,
        }

        async def edit_publication(
            group_state: dict[str, int] = group_state,
        ) -> None:
            await context.ui.edit(
                control,
                text(
                    job.language,
                    "publishing",
                    icon=context.premium.html("UPLOAD"),
                    prepared=group_state["prepared"],
                    done=group_state["published"],
                    total=len(outputs),
                    **context.premium.placeholders(),
                ),
                reply_markup=processing_keyboard(
                    context.premium, job.job_id, job.language
                ),
            )

        async def preparation_progress(
            done: int,
            _total: int,
            group_state: dict[str, int] = group_state,
        ) -> None:
            nonlocal prepared, last_publication_update
            prepared = group_state["offset"] + done
            group_state["prepared"] = prepared
            now = time.monotonic()
            if now - last_publication_update < 1.0 and prepared != len(outputs):
                return
            last_publication_update = now
            with contextlib.suppress(Exception):
                await edit_publication()

        async def publication_progress(
            done: int,
            _total: int,
            group_state: dict[str, int] = group_state,
        ) -> None:
            nonlocal published, last_publication_update
            published = group_state["offset"] + done
            group_state["published"] = published
            job.progress = published
            now = time.monotonic()
            if now - last_publication_update < 1.0 and published != len(outputs):
                return
            last_publication_update = now
            with contextlib.suppress(Exception):
                await context.ui.edit(
                    control,
                    text(
                        job.language,
                        "publishing",
                        icon=context.premium.html("UPLOAD"),
                        prepared=group_state["prepared"],
                        done=published,
                        total=len(outputs),
                        **context.premium.placeholders(),
                    ),
                    reply_markup=processing_keyboard(
                        context.premium, job.job_id, job.language
                    ),
                )

        async def publication_flood(
            remaining: float,
            group_state: dict[str, int] = group_state,
        ) -> None:
            await _show_flood_wait(
                control,
                job,
                context,
                remaining,
                done=group_state["published"],
                total=len(outputs),
                publishing=True,
                prepared=group_state["prepared"],
            )

        if len(groups) == 1:
            part_title = title
        else:
            suffix = f" — Part {index}"
            part_title = f"{title[: 64 - len(suffix)].rstrip()}{suffix}"
        files = [
            (path, detect_format(path), item.emoji_list)
            for item, path in group
        ]
        name = await context.publisher.publish_set(
            user_id=job.user_id,
            title=part_title,
            bot_username=context.bot_username,
            files=files,
            custom_emoji=custom,
            needs_repainting=job.adaptive,
            cancel_event=job.cancel_event,
            on_flood=publication_flood,
            on_progress=publication_progress,
            on_prepare=preparation_progress,
        )
        prepared = group_offset + len(group)
        published = group_offset + len(group)
        job.progress = published
        job.created_sets.append(name)
        url = pack_url(name, custom_emoji=custom)
        links.append(url)
        saved_packs.append(
            {
                "title": part_title,
                "url": url,
                "kind": "emoji" if custom else "sticker",
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
    if job.is_admin:
        await context.admins.remember_packs(job.user_id, saved_packs)
    await context.database.increment_statistics(
        {"emoji_packs_created" if custom else "sticker_packs_created": len(links)}
    )
    link_lines = "\n".join(
        f'<a href="{html.escape(url, quote=True)}">'
        f'{"Часть" if job.language == "ru" else "Part"} {index}</a>'
        for index, url in enumerate(links, 1)
    )
    if job.language == "ru":
        kind_label = "Emoji-набор" if custom else "Набор стикеров"
    else:
        kind_label = "Emoji Pack" if custom else "Sticker Pack"
    body = text(
        job.language,
        "done_pack",
        icon=context.premium.html("SUCCESS"),
        title=html.escape(title),
        kind=kind_label,
        count=len(outputs),
        color=job.selected_color or "Adaptive",
        **context.premium.placeholders(),
    )
    if len(links) > 1:
        body += f"\n\n{link_lines}"
    if job.errors:
        body += "\n\n" + _error_summary(job)
    await context.ui.edit(
        control,
        body,
        reply_markup=result_keyboard(
            context.premium, add_url=links[0], language=job.language
        ),
    )


def _error_summary(job: RuntimeJob) -> str:
    heading = text(
        job.language,
        "partial",
        done=job.progress,
        total=job.total,
        failed=len(job.errors),
    )
    details = "\n".join(
        f"#{index}: {html.escape(reason)}" for index, reason in job.errors[:20]
    )
    if len(job.errors) > 20:
        details += f"\n… +{len(job.errors) - 20}"
    return f"{heading}\n{details}"


@router.callback_query(F.data == "restart")
async def restart_callback(callback: CallbackQuery, context: AppContext) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        language = context.languages.get(
            callback.from_user.id,
            "ru",
        )
        await show_main_menu(callback.message, context, language)


@router.callback_query(F.data.startswith("job:"))
async def job_callback(callback: CallbackQuery, context: AppContext) -> None:
    data = callback.data or ""
    parts = data.split(":")
    if len(parts) < 3 or not isinstance(callback.message, Message):
        return
    job_id, action = parts[1], parts[2]
    is_admin = await context.admins.is_admin(callback.from_user.id)
    job = context.jobs.owned(job_id, callback.from_user.id, administrator=is_admin)
    if job is None:
        return
    await callback.answer()
    job.touch()
    control = callback.message
    if action == "cancel":
        job.request_cancel()
        await context.ui.edit(
            control,
            text(job.language, "cancelled", icon=context.premium.html("CANCEL")),
        )
        cancelled = await context.jobs.cancel(job.job_id)
        if cancelled and cancelled.created_sets:
            await context.publisher.delete_sets(cancelled.created_sets)
        return
    if action == "restart":
        await _delete_old_preview(job, context)
        await context.jobs.finish(job.job_id, JobStatus.COMPLETED)
        await show_main_menu(control, context, job.language)
        return
    if action == "single_pack":
        job.output_type = OutputType.EMOJI_PACK
        await _request_pack_name(control, job, context)
        return
    if action == "download":
        if job.source is None:
            return
        job.status = JobStatus.PROCESSING
        await context.ui.edit(
            control,
            text(
                job.language,
                "preparing_download",
                icon=context.premium.html("DOWNLOAD"),
            ),
            reply_markup=processing_keyboard(
                context.premium, job.job_id, job.language
            ),
        )
        job.output_type = OutputType.FILE
        try:
            path = await context.pipeline.process_item(job, job.source.items[0])
            await _telegram_send(
                lambda: control.answer_document(
                    FSInputFile(path, filename=f"recolored{path.suffix.lower()}"),
                    disable_content_type_detection=True,
                ),
                control,
                job,
                context,
            )
        except Exception as error:
            context.errors.add(job_id=job.job_id, component="download", error=error)
            await _source_error(control, job.language, context, error)
        finally:
            job.output_type = OutputType.STICKER_PACK
            job.status = JobStatus.AWAITING_RESULT_ACTION
        await context.ui.edit(
            control,
            text(
                job.language,
                "single_result_ready",
                icon=context.premium.html("SUCCESS"),
                color=job.selected_color or "Adaptive",
                **context.premium.placeholders(),
            ),
            reply_markup=single_result_keyboard(
                context.premium, job.job_id, job.language
            ),
        )
        return
    if action == "color" and len(parts) == 4:
        await _select_color(control, job, parts[3], context)
    elif action == "recolor":
        job.status = JobStatus.AWAITING_COLOR
        await context.ui.edit(
            control,
            text(
                job.language,
                "colors",
                icon=context.premium.html("COLOR"),
            ),
            reply_markup=color_keyboard(
                context.premium,
                job.job_id,
                context.settings.color_picker_url,
                language=job.language,
            ),
        )
    elif action == "continue":
        job.status = JobStatus.AWAITING_OUTPUT_TYPE
        key = (
            "pack_choose_output"
            if job.source is not None and job.source.kind == SourceKind.PACK
            else "choose_output"
        )
        await context.ui.edit(
            control,
            text(
                job.language,
                key,
                icon=context.premium.html("COLOR"),
                color=job.selected_color,
                count=job.total,
                **context.premium.placeholders(),
            ),
            reply_markup=output_keyboard(
                context.premium, job.job_id, single=False, language=job.language
            ),
        )
    elif action == "adaptive":
        job.adaptive = True
        job.selected_color = None
        job.output_type = OutputType.EMOJI_PACK
        job.status = JobStatus.AWAITING_PREVIEW_DECISION
        if job.source:
            item = job.source.items[0]
            try:
                preview_path = await context.pipeline.process_item(
                    job, item, preview=True
                )
                preview_format = (
                    MediaFormat.PNG
                    if preview_path.suffix.lower() == ".png"
                    else item.format
                )
                await _send_preview(
                    control, job, preview_path, preview_format, context
                )
            except Exception as error:
                context.errors.add(
                    job_id=job.job_id,
                    component="adaptive_preview",
                    error=error,
                )
                await _source_error(control, job.language, context, error)
                job.status = JobStatus.AWAITING_COLOR
                return
        await context.ui.edit(
            control,
            text(job.language, "adaptive_preview", icon=context.premium.html("MAGIC")),
            reply_markup=adaptive_preview_keyboard(
                context.premium, job.job_id, job.language
            ),
        )
    elif action == "adaptive_ok":
        await _request_pack_name(control, job, context)
    elif action == "out" and len(parts) == 4:
        try:
            job.output_type = OutputType(parts[3])
        except ValueError:
            return
        if job.output_type in {OutputType.EMOJI_PACK, OutputType.STICKER_PACK}:
            await _request_pack_name(control, job, context)
        else:
            await _start_processing(control, job, context)
    elif action == "source_title" and job.source and job.source.title:
        job.pack_title = job.source.title[:64]
        await _start_processing(control, job, context)
    elif action == "split":
        job.split_allowed = True
        await _start_processing(control, job, context)
