"""Private-chat source, color, preview, output, publishing and cleanup workflow."""

from __future__ import annotations

import asyncio
import contextlib
import html
import logging
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace
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
    existing_pack_keyboard,
    intensity_keyboard,
    output_keyboard,
    pack_name_keyboard,
    preview_keyboard,
    processing_keyboard,
    result_keyboard,
    single_result_keyboard,
    split_keyboard,
)
from app.logging import safe_error
from app.models.job import JobStatus, OutputType, RecolorIntensity, RuntimeJob
from app.models.source import MediaFormat, SourceItem, SourceKind
from app.recolor.color_math import parse_colors
from app.services.archive import split_output_zip
from app.services.jobs import ActiveJobError
from app.services.source_resolver import (
    SourceError,
    find_pack_link,
    message_pack_link,
    resolve_media_group,
    resolve_message,
)
from app.services.telegram_stickers import pack_url
from app.services.unicode_emoji import extract_emojis
from app.services.user_rate_limiter import RateLimitExceeded, classify_job
from app.validators.common import detect_format
from app.validators.source import SourceValidationError

LOGGER = logging.getLogger(__name__)
router = Router(name="workflow")
MAX_COLORS_PER_JOB = 10


def _countdown(seconds: float) -> str:
    total = max(0, math.ceil(seconds))
    minutes, remainder = divmod(total, 60)
    return f"{minutes:02d}:{remainder:02d}"


async def _pack_eta(
    context: AppContext,
    remaining_items: int,
    *,
    known_wait: float = 0.0,
) -> str:
    local_wait = await context.telegram_limiter.estimate_conservative_delay(
        remaining_items
    )
    # Telegram API calls and the final thumbnail update usually take a few
    # seconds in addition to the mutation window. Keep this explicitly
    # approximate instead of promising an exact completion time.
    api_overhead = remaining_items * 1.5 if remaining_items else 0.0
    return _countdown(max(known_wait, local_wait) + api_overhead)


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
        now = time.monotonic()
        if (
            remaining > 5
            and job.last_ui_update_at > 0
            and now - job.last_ui_update_at < 15
        ):
            return
        job.last_ui_update_at = now
        completed = job.progress if done is None else done
        expected_total = job.total if total is None else total
        eta = await _pack_eta(
            context,
            max(0, expected_total - completed),
            known_wait=remaining,
        )
        await context.ui.edit(
            control,
            f'{context.premium.html("TIME")} '
            + text(
                job.language,
                "pack_flood_wait" if publishing else "flood_wait",
                seconds=_countdown(remaining),
                done=completed,
                total=expected_total,
                prepared=job.progress if prepared is None else prepared,
                eta=eta,
                **context.premium.placeholders(),
            ),
            reply_markup=processing_keyboard(
                context.premium, job.job_id, job.language
            ),
            retry_as_answer=False,
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
        conservative=False,
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
    if isinstance(error, SourceValidationError):
        await context.ui.answer(
            message,
            f'{context.premium.html("ERROR")} {text(language, error.message_key)}',
        )
        return
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
        job.base_errors = list(job.errors)
        extracted = sum(item.path.stat().st_size for item in source.items)
        webm = sum(item.format == MediaFormat.WEBM for item in source.items)
        tgs = sum(item.format == MediaFormat.TGS for item in source.items)
        await context.user_limiter.check_and_record(
            user_id,
            is_admin=is_admin,
            weight=classify_job(
                items=len(source.items),
                extracted_bytes=extracted,
                webm_items=webm,
                tgs_items=tgs,
            ),
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
        or extract_emojis(value) is not None
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
            job.status == JobStatus.AWAITING_TARGET_PACK
            and message.text
        ):
            await _handle_existing_pack_link(message, job, context)
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
    path, media_format = await context.pipeline.prepare_chat_sticker(
        job, path, media_format
    )
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
            chat_id=job.chat_id,
            path=path,
            media_format=media_format,
            cancel_event=job.cancel_event,
            on_flood=lambda remaining: _show_flood_wait(
                control, job, context, remaining
            ),
        )
    job.preview_message_id = preview.message_id


def _intensity_label(job: RuntimeJob) -> str:
    return text(job.language, f"intensity_{job.intensity.value}")


def _color_summary(job: RuntimeJob) -> str:
    if job.adaptive:
        return "Adaptive"
    return ", ".join(job.selected_colors) or job.selected_color or "—"


def _build_work_items(job: RuntimeJob) -> None:
    if job.source is None:
        job.work_items = []
        return
    if job.adaptive:
        job.work_items = list(job.source.items)
        job.total = len(job.work_items) + len(job.base_errors)
        return
    colors = job.selected_colors or ([job.selected_color] if job.selected_color else [])
    variants: list[SourceItem] = []
    for color in colors:
        for source_item in job.source.items:
            variants.append(
                replace(
                    source_item,
                    index=len(variants) + 1,
                    target_color=color,
                    source_index=source_item.index,
                )
            )
    job.work_items = variants
    job.total = len(variants) + len(job.base_errors)


async def _show_intensity_choice(
    control: Message, job: RuntimeJob, context: AppContext
) -> None:
    if job.source is None:
        return
    job.status = JobStatus.AWAITING_INTENSITY
    await context.ui.edit(
        control,
        text(
            job.language,
            "choose_intensity",
            icon=context.premium.html("COLOR"),
            source_count=len(job.source.items),
            color_count=len(job.selected_colors),
            result_count=len(job.work_items),
            colors=_color_summary(job),
        ),
        reply_markup=intensity_keyboard(
            context.premium,
            job.job_id,
            job.language,
        ),
    )


async def _start_after_intensity(
    control: Message, job: RuntimeJob, context: AppContext
) -> None:
    job.direct_result = len(job.processing_items) == 1
    if job.direct_result:
        job.output_type = OutputType.STICKER_PACK
        job.status = JobStatus.PROCESSING
        task = asyncio.create_task(
            _run_single_result(control, job, context),
            name=f"single-{job.short_id}",
        )
        job.processing_task = task
        return
    await _render_preview(control, job, context)


async def _render_preview(
    control: Message, job: RuntimeJob, context: AppContext
) -> None:
    if job.source is None:
        return
    job.status = JobStatus.GENERATING_PREVIEW
    preview_error: Exception | None = None
    for preview_item in job.processing_items:
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
            intensity=_intensity_label(job),
            **context.premium.placeholders(),
        ),
        reply_markup=preview_keyboard(
            context.premium,
            job.job_id,
            job.language,
            job.intensity,
        ),
    )


async def _select_color(
    control: Message, job: RuntimeJob, color_value: str, context: AppContext
) -> None:
    try:
        colors = parse_colors(color_value)
    except ValueError:
        await context.ui.answer(
            control,
            f'{context.premium.html("ERROR")} {text(job.language, "invalid_color")}',
        )
        return
    if job.source is None:
        return
    result_count = len(job.source.items) * len(colors)
    if (
        len(colors) > MAX_COLORS_PER_JOB
        or result_count > context.settings.max_logical_items
    ):
        await context.ui.answer(
            control,
            f'{context.premium.html("ERROR")} '
            + text(
                job.language,
                "too_many_colors",
                maximum_colors=MAX_COLORS_PER_JOB,
                maximum_items=context.settings.max_logical_items,
            ),
        )
        return
    if not job.is_admin and job.color_changes >= context.limits.preview_color_changes:
        await context.ui.answer(
            control,
            f'{context.premium.html("TIME")} {text(job.language, "rate_limited")}',
        )
        return
    job.color_changes += 1
    job.selected_colors = [color.hex for color in colors]
    job.selected_color = job.selected_colors[0]
    job.adaptive = False
    job.errors = list(job.base_errors)
    job.failed_items = []
    _build_work_items(job)
    job.touch()
    await _show_intensity_choice(control, job, context)


async def _handle_color_text(message: Message, job: RuntimeJob, context: AppContext) -> None:
    try:
        colors = parse_colors(message.text or "")
    except ValueError:
        await context.ui.answer(
            message,
            f'{context.premium.html("ERROR")} {text(job.language, "invalid_color")}',
        )
        return
    if job.source is None:
        return
    if (
        len(colors) > MAX_COLORS_PER_JOB
        or len(colors) * len(job.source.items) > context.settings.max_logical_items
    ):
        await context.ui.answer(
            message,
            f'{context.premium.html("ERROR")} '
            + text(
                job.language,
                "too_many_colors",
                maximum_colors=MAX_COLORS_PER_JOB,
                maximum_items=context.settings.max_logical_items,
            ),
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


async def _show_existing_pack_link_prompt(
    control: Message, job: RuntimeJob, context: AppContext
) -> None:
    job.status = JobStatus.AWAITING_TARGET_PACK
    await context.ui.edit(
        control,
        f'{context.premium.html("LINK")} '
        + text(job.language, "existing_pack_link_prompt"),
        reply_markup=pack_name_keyboard(
            context.premium,
            job.job_id,
            source_title=False,
            language=job.language,
            back_action=(
                "existing"
                if job.is_admin and job.target_pack_options
                else "pack_back"
            ),
        ),
    )


async def _request_existing_pack(
    control: Message, job: RuntimeJob, context: AppContext
) -> None:
    job.status = JobStatus.AWAITING_TARGET_PACK
    job.target_pack_name = None
    job.target_pack_title = None
    job.target_pack_options = []
    if job.is_admin:
        job.target_pack_options = (await context.admins.packs(job.user_id))[-12:]
    if not job.target_pack_options:
        await _show_existing_pack_link_prompt(control, job, context)
        return
    await context.ui.edit(
        control,
        f'{context.premium.html("PACK")} '
        + text(job.language, "existing_pack_admin_prompt"),
        reply_markup=existing_pack_keyboard(
            context.premium,
            job.job_id,
            job.target_pack_options,
            job.language,
        ),
    )


async def _return_from_pack_choice(
    control: Message, job: RuntimeJob, context: AppContext
) -> None:
    """Return to the screen from which pack creation/addition was opened."""

    job.target_pack_name = None
    job.target_pack_title = None
    job.target_pack_options = []
    if job.adaptive:
        job.status = JobStatus.AWAITING_PREVIEW_DECISION
        await context.ui.edit(
            control,
            text(
                job.language,
                "adaptive_preview",
                icon=context.premium.html("MAGIC"),
            ),
            reply_markup=adaptive_preview_keyboard(
                context.premium, job.job_id, job.language
            ),
        )
        return
    if job.direct_result or (
        job.source is not None
        and len(job.source.items) == 1
        and len(job.selected_colors) <= 1
    ):
        job.output_type = OutputType.STICKER_PACK
        job.status = JobStatus.AWAITING_RESULT_ACTION
        await context.ui.edit(
            control,
            text(
                job.language,
                "single_result_ready",
                icon=context.premium.html("SUCCESS"),
                color=_color_summary(job),
                intensity=_intensity_label(job),
                **context.premium.placeholders(),
            ),
            reply_markup=single_result_keyboard(
                context.premium, job.job_id, job.language, job.intensity
            ),
        )
        return
    job.output_type = None
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
            color=_color_summary(job),
            count=job.total,
            **context.premium.placeholders(),
        ),
        reply_markup=output_keyboard(
            context.premium, job.job_id, single=False, language=job.language
        ),
    )


async def _select_existing_pack(
    control: Message,
    job: RuntimeJob,
    context: AppContext,
    value: str,
) -> bool:
    parsed = find_pack_link(value)
    if parsed is None:
        await context.ui.answer(
            control,
            f'{context.premium.html("ERROR")} '
            + text(job.language, "existing_pack_invalid_link"),
        )
        return False
    route, name = parsed
    suffix = f"_by_{context.bot_username}".lower()
    if not name.lower().endswith(suffix):
        await context.ui.answer(
            control,
            f'{context.premium.html("ERROR")} '
            + text(job.language, "existing_pack_wrong_bot"),
        )
        return False
    try:
        sticker_set = await context.bot.get_sticker_set(name)
    except Exception:
        await context.ui.answer(
            control,
            f'{context.premium.html("ERROR")} '
            + text(job.language, "existing_pack_unavailable"),
        )
        return False
    raw_sticker_type = sticker_set.sticker_type
    sticker_type = str(getattr(raw_sticker_type, "value", raw_sticker_type))
    if sticker_type == "mask" or (
        route == "addemoji" and sticker_type != "custom_emoji"
    ) or (route == "addstickers" and sticker_type != "regular"):
        await context.ui.answer(
            control,
            f'{context.premium.html("ERROR")} '
            + text(job.language, "existing_pack_type_mismatch"),
        )
        return False
    custom = sticker_type == "custom_emoji"
    if job.adaptive and not custom:
        await context.ui.answer(
            control,
            f'{context.premium.html("ERROR")} '
            + text(job.language, "existing_pack_adaptive_mismatch"),
        )
        return False
    maximum = TELEGRAM_CUSTOM_EMOJI_SET_MAX if custom else TELEGRAM_REGULAR_STICKER_SET_MAX
    incoming = len(job.processing_items)
    if len(sticker_set.stickers) + incoming > maximum:
        await context.ui.answer(
            control,
            f'{context.premium.html("ERROR")} '
            + text(
                job.language,
                "existing_pack_full",
                current=len(sticker_set.stickers),
                incoming=incoming,
                maximum=maximum,
            ),
        )
        return False
    target_adaptive = bool(
        sticker_set.stickers and sticker_set.stickers[0].needs_repainting
    )
    if custom and target_adaptive != job.adaptive:
        await context.ui.answer(
            control,
            f'{context.premium.html("ERROR")} '
            + text(job.language, "existing_pack_adaptive_mismatch"),
        )
        return False
    job.target_pack_name = name
    job.target_pack_title = sticker_set.title
    job.output_type = OutputType.EMOJI_PACK if custom else OutputType.STICKER_PACK
    job.appended_items = 0
    await context.ui.edit(
        control,
        text(
            job.language,
            "processing",
            icon=context.premium.html("LOADING"),
            done=0,
            total=max(1, incoming),
        ),
        reply_markup=processing_keyboard(context.premium, job.job_id, job.language),
    )
    await _start_processing(control, job, context)
    return True


async def _handle_existing_pack_link(
    message: Message, job: RuntimeJob, context: AppContext
) -> None:
    control: Message | None = None
    if job.control_message_id is not None:
        try:
            edited = await context.bot.edit_message_text(
                chat_id=job.chat_id,
                message_id=job.control_message_id,
                text=f'{context.premium.html("LOADING")} '
                + text(job.language, "existing_pack_checking"),
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
            f'{context.premium.html("LOADING")} '
            + text(job.language, "existing_pack_checking"),
            reply_markup=processing_keyboard(
                context.premium, job.job_id, job.language
            ),
        )
        job.control_message_id = control.message_id
    accepted = await _select_existing_pack(
        control, job, context, message.text or ""
    )
    if not accepted:
        await _show_existing_pack_link_prompt(control, job, context)
    with contextlib.suppress(Exception):
        await message.delete()


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
    if job.processing_task is not None and not job.processing_task.done():
        return
    if (
        job.output_type in {OutputType.EMOJI_PACK, OutputType.STICKER_PACK}
        and job.target_pack_name is None
    ):
        maximum = (
            TELEGRAM_CUSTOM_EMOJI_SET_MAX
            if job.output_type == OutputType.EMOJI_PACK
            else TELEGRAM_REGULAR_STICKER_SET_MAX
        )
        if len(job.processing_items) > maximum and not job.split_allowed:
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
        delivery_path, delivery_format = await context.pipeline.prepare_chat_sticker(
            job, path, detect_format(path)
        )
        await _delete_old_preview(job, context)
        delivered = await context.publisher.send_sticker_file(
            chat_id=job.chat_id,
            path=delivery_path,
            media_format=delivery_format,
            cancel_event=job.cancel_event,
            on_flood=lambda remaining: _show_flood_wait(
                control, job, context, remaining, done=1, total=1
            ),
        )
        job.preview_message_id = delivered.message_id
        job.status = JobStatus.AWAITING_RESULT_ACTION
        await context.ui.edit(
            control,
            text(
                job.language,
                "single_result_ready",
                icon=context.premium.html("SUCCESS"),
                color=_color_summary(job),
                intensity=_intensity_label(job),
                **context.premium.placeholders(),
            ),
            reply_markup=single_result_keyboard(
                context.premium, job.job_id, job.language, job.intensity
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
        if job.failed_items:
            job.status = JobStatus.AWAITING_RETRY
            body = (
                f'{context.premium.html("ERROR")} '
                + text(job.language, "service_error")
                + "\n\n"
                + _error_summary(job)
            )
            with contextlib.suppress(Exception):
                await context.ui.edit(
                    control,
                    body,
                    reply_markup=result_keyboard(
                        context.premium,
                        language=job.language,
                        job_id=job.job_id,
                        retry_errors=True,
                    ),
                )
            job.processing_task = None
            job.touch()
            return
        await context.jobs.finish(job.job_id, JobStatus.FAILED)


async def _run_job(control: Message, job: RuntimeJob, context: AppContext) -> None:
    started = time.monotonic()
    last_progress = 0.0
    final_status = JobStatus.COMPLETED

    async def progress(done: int, total: int) -> None:
        nonlocal last_progress
        now = time.monotonic()
        if now - last_progress < 5.0 and done != total:
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
                retry_as_answer=False,
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
                    color=_color_summary(job),
                    **context.premium.placeholders(),
                ),
                reply_markup=result_keyboard(
                    context.premium,
                    language=job.language,
                    job_id=job.job_id,
                    retry_errors=bool(job.failed_items),
                ),
            )
        elif job.output_type == OutputType.ZIP:
            await _deliver_zip(control, job, [path for _, path in outputs], context)
        elif job.target_pack_name is not None:
            await _append_existing_pack(control, job, outputs, context)
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
            if job.target_pack_name is not None:
                body = text(
                    job.language,
                    "existing_pack_add_failed",
                    icon=context.premium.html("ERROR"),
                    done=job.appended_items,
                    total=job.publication_total,
                )
            else:
                body = text(
                    job.language,
                    "service_error",
                    icon=context.premium.html("ERROR"),
                )
            if job.errors:
                body += "\n\n" + _error_summary(job)
            await context.ui.edit(
                control,
                body,
                reply_markup=result_keyboard(
                    context.premium,
                    language=job.language,
                    job_id=job.job_id,
                    retry_errors=bool(job.failed_items),
                ),
            )
    finally:
        await _delete_old_preview(job, context)
        job.processing_task = None
        if job.failed_items and final_status != JobStatus.CANCELLED:
            job.status = JobStatus.AWAITING_RETRY
            job.touch()
        else:
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
        selected_color=_color_summary(job),
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
        color=_color_summary(job),
        **context.premium.placeholders(),
    )
    if job.errors:
        body += "\n\n" + _error_summary(job)
    await context.ui.edit(
        control,
        body,
        reply_markup=result_keyboard(
            context.premium,
            language=job.language,
            job_id=job.job_id,
            retry_errors=bool(job.failed_items),
        ),
    )


async def _append_existing_pack(
    control: Message,
    job: RuntimeJob,
    outputs: list[tuple[SourceItem, Path]],
    context: AppContext,
) -> None:
    if job.target_pack_name is None or job.output_type is None:
        raise RuntimeError("Existing target pack is missing")
    custom = job.output_type == OutputType.EMOJI_PACK
    job.status = JobStatus.PUBLISHING
    job.appended_items = 0
    job.publication_total = len(outputs)
    job.progress = 0
    eta = await _pack_eta(context, len(outputs))
    await context.ui.edit(
        control,
        text(
            job.language,
            "publishing_existing",
            icon=context.premium.html("UPLOAD"),
            title=html.escape(job.target_pack_title or job.target_pack_name),
            done=0,
            total=len(outputs),
            eta=eta,
            **context.premium.placeholders(),
        ),
        reply_markup=processing_keyboard(context.premium, job.job_id, job.language),
    )
    last_update = 0.0

    async def progress(done: int, total: int) -> None:
        nonlocal last_update
        job.appended_items = done
        job.progress = done
        now = time.monotonic()
        if now - last_update < 5.0 and done != total:
            return
        last_update = now
        remaining_eta = await _pack_eta(context, max(0, total - done))
        await context.ui.edit(
            control,
            text(
                job.language,
                "publishing_existing",
                icon=context.premium.html("UPLOAD"),
                title=html.escape(job.target_pack_title or job.target_pack_name or "—"),
                done=done,
                total=total,
                eta=remaining_eta,
                **context.premium.placeholders(),
            ),
            reply_markup=processing_keyboard(
                context.premium, job.job_id, job.language
            ),
            retry_as_answer=False,
        )

    async def flood(remaining: float) -> None:
        await _show_flood_wait(
            control,
            job,
            context,
            remaining,
            done=job.appended_items,
            total=len(outputs),
            publishing=True,
            prepared=len(outputs),
        )

    files = [
        (path, detect_format(path), item.emoji_list)
        for item, path in outputs
    ]

    async def item_error(position: int, error: Exception) -> None:
        item = outputs[position - 1][0]
        job.errors.append((item.index, "message_key:telegram_item_rejected"))
        job.failed_items.append(item)
        context.errors.add(
            job_id=job.job_id,
            component=f"existing_pack_item_{item.index}",
            error=error,
        )

    failed = await context.publisher.append_to_set(
        user_id=job.user_id,
        name=job.target_pack_name,
        files=files,
        cancel_event=job.cancel_event,
        on_flood=flood,
        on_progress=progress,
        on_error=item_error,
    )
    if failed and job.appended_items == 0:
        raise RuntimeError("Telegram rejected every prepared sticker")
    url = pack_url(job.target_pack_name, custom_emoji=custom)
    body = text(
        job.language,
        "done_existing_pack",
        icon=context.premium.html("SUCCESS"),
        title=html.escape(job.target_pack_title or job.target_pack_name),
        count=job.appended_items,
        **context.premium.placeholders(),
    )
    if job.errors:
        body += "\n\n" + _error_summary(job)
    await context.ui.edit(
        control,
        body,
        reply_markup=result_keyboard(
            context.premium,
            add_url=url,
            language=job.language,
            job_id=job.job_id,
            retry_errors=bool(job.failed_items),
        ),
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
    job.publication_total = len(outputs)
    job.progress = 0
    initial_eta = await _pack_eta(context, len(outputs))
    await context.ui.edit(
        control,
        text(
            job.language,
            "publishing",
            icon=context.premium.html("UPLOAD"),
            prepared=len(outputs),
            done=0,
            total=len(outputs),
            eta=initial_eta,
            **context.premium.placeholders(),
        ),
        reply_markup=processing_keyboard(context.premium, job.job_id, job.language),
    )
    groups = [outputs[index : index + maximum] for index in range(0, len(outputs), maximum)]
    links: list[str] = []
    saved_packs: list[dict[str, str]] = []
    published = 0
    last_publication_update = 0.0
    for index, group in enumerate(groups, 1):
        group_offset = published
        group_state = {
            "offset": group_offset,
            "prepared": len(outputs),
            "published": published,
        }

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
            if now - last_publication_update < 5.0 and published != len(outputs):
                return
            last_publication_update = now
            eta = await _pack_eta(context, max(0, len(outputs) - published))
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
                        eta=eta,
                        **context.premium.placeholders(),
                    ),
                    reply_markup=processing_keyboard(
                        context.premium, job.job_id, job.language
                    ),
                    retry_as_answer=False,
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
        try:
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
            )
        except Exception as error:
            job.failed_items.extend(item for item, _ in group)
            reason = str(error).strip() or type(error).__name__
            job.errors.extend((item.index, reason) for item, _ in group)
            raise
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
        color=_color_summary(job),
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
            context.premium,
            add_url=links[0],
            language=job.language,
            job_id=job.job_id,
            retry_errors=bool(job.failed_items),
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
    def localize_reason(reason: str) -> str:
        prefix = "message_key:"
        if reason.startswith(prefix):
            return text(job.language, reason.removeprefix(prefix))
        return html.escape(reason)

    details = "\n".join(
        f"#{index}: {localize_reason(reason)}" for index, reason in job.errors[:20]
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
    if action in {"restart", "home"}:
        await _delete_old_preview(job, context)
        await context.jobs.finish(job.job_id, JobStatus.COMPLETED)
        await show_main_menu(control, context, job.language)
        return
    if action == "existing":
        await _request_existing_pack(control, job, context)
        return
    if action == "existing_link":
        await _show_existing_pack_link_prompt(control, job, context)
        return
    if action == "pack_back":
        await _return_from_pack_choice(control, job, context)
        return
    if action == "retry_failed":
        if job.status != JobStatus.AWAITING_RETRY or not job.failed_items:
            return
        retry_items = list(job.failed_items)
        job.work_items = retry_items
        job.failed_items = []
        job.errors = list(job.base_errors)
        job.progress = 0
        job.total = len(retry_items) + len(job.base_errors)
        job.cancel_event = asyncio.Event()
        if (
            job.output_type in {OutputType.EMOJI_PACK, OutputType.STICKER_PACK}
            and job.target_pack_name is None
            and len(job.created_sets) == 1
        ):
            maximum = (
                TELEGRAM_CUSTOM_EMOJI_SET_MAX
                if job.output_type == OutputType.EMOJI_PACK
                else TELEGRAM_REGULAR_STICKER_SET_MAX
            )
            if job.publication_total <= maximum:
                job.target_pack_name = job.created_sets[0]
                job.target_pack_title = job.pack_title or "Recolored"
        await context.ui.edit(
            control,
            text(
                job.language,
                "retry_failed",
                icon=context.premium.html("LOADING"),
                count=len(retry_items),
            ),
            reply_markup=processing_keyboard(
                context.premium, job.job_id, job.language
            ),
        )
        if job.direct_result:
            job.status = JobStatus.PROCESSING
            task = asyncio.create_task(
                _run_single_result(control, job, context),
                name=f"retry-single-{job.short_id}",
            )
            job.processing_task = task
        else:
            await _start_processing(control, job, context)
        return
    if action == "intensity_back":
        job.status = JobStatus.AWAITING_COLOR
        await context.ui.edit(
            control,
            text(job.language, "colors", icon=context.premium.html("COLOR")),
            reply_markup=color_keyboard(
                context.premium,
                job.job_id,
                context.settings.color_picker_url,
                language=job.language,
            ),
        )
        return
    if action == "choose_intensity" and len(parts) == 4:
        if job.adaptive or job.status != JobStatus.AWAITING_INTENSITY:
            return
        try:
            job.intensity = RecolorIntensity(parts[3])
        except ValueError:
            return
        await _start_after_intensity(control, job, context)
        return
    if action == "existing_saved" and len(parts) == 4:
        try:
            selected = job.target_pack_options[int(parts[3])]
        except (IndexError, KeyError, TypeError, ValueError):
            await _request_existing_pack(control, job, context)
            return
        accepted = await _select_existing_pack(
            control,
            job,
            context,
            selected.get("url", ""),
        )
        if not accepted:
            await _request_existing_pack(control, job, context)
        return
    if action == "single_pack":
        job.target_pack_name = None
        job.target_pack_title = None
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
            path = await context.pipeline.process_item(job, job.processing_items[0])
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
                color=_color_summary(job),
                intensity=_intensity_label(job),
                **context.premium.placeholders(),
            ),
            reply_markup=single_result_keyboard(
                context.premium, job.job_id, job.language, job.intensity
            ),
        )
        return
    if action == "intensity" and len(parts) == 4:
        if job.adaptive or job.source is None:
            return
        if job.processing_task is not None and not job.processing_task.done():
            return
        try:
            selected_intensity = RecolorIntensity(parts[3])
        except ValueError:
            return
        if selected_intensity == job.intensity:
            return
        job.intensity = selected_intensity
        if job.direct_result:
            job.output_type = OutputType.STICKER_PACK
            job.status = JobStatus.PROCESSING
            task = asyncio.create_task(
                _run_single_result(control, job, context),
                name=f"intensity-{job.short_id}",
            )
            job.processing_task = task
        else:
            await _render_preview(control, job, context)
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
                color=_color_summary(job),
                count=len(job.processing_items),
                **context.premium.placeholders(),
            ),
            reply_markup=output_keyboard(
                context.premium, job.job_id, single=False, language=job.language
            ),
        )
    elif action == "adaptive":
        job.adaptive = True
        job.selected_color = None
        job.selected_colors = []
        job.errors = list(job.base_errors)
        job.failed_items = []
        _build_work_items(job)
        job.direct_result = False
        job.output_type = OutputType.EMOJI_PACK
        job.status = JobStatus.AWAITING_PREVIEW_DECISION
        if job.source:
            item = job.processing_items[0]
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
        job.target_pack_name = None
        job.target_pack_title = None
        await _request_pack_name(control, job, context)
    elif action == "out" and len(parts) == 4:
        try:
            job.output_type = OutputType(parts[3])
        except ValueError:
            return
        if job.output_type in {OutputType.EMOJI_PACK, OutputType.STICKER_PACK}:
            job.target_pack_name = None
            job.target_pack_title = None
            await _request_pack_name(control, job, context)
        else:
            await _start_processing(control, job, context)
    elif action == "source_title" and job.source and job.source.title:
        job.target_pack_name = None
        job.target_pack_title = None
        job.pack_title = job.source.title[:64]
        await _start_processing(control, job, context)
    elif action == "split":
        job.split_allowed = True
        await _start_processing(control, job, context)
