"""Strict source identification without arbitrary HTTP fetching."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import unquote, urlparse

from aiogram import Bot
from aiogram.enums import MessageEntityType
from aiogram.types import Message, Sticker

from app.config import Settings
from app.models.job import RuntimeJob
from app.models.source import MediaFormat, SourceDescriptor, SourceItem, SourceKind
from app.services.archive import extract_zip
from app.services.telegram_files import (
    download_document,
    download_sticker,
    download_thumbnail,
    sticker_extension,
)
from app.services.unicode_emoji import extract_emojis, render_emoji
from app.validators.source import SourceValidationError, validate_source_file


class SourceError(ValueError):
    """The Telegram message cannot be resolved into a safe supported source."""


def _job_error_reason(error: Exception) -> str:
    if isinstance(error, SourceValidationError):
        return f"message_key:{error.message_key}"
    return str(error).strip() or type(error).__name__


PACK_LINK_RE = re.compile(
    r"(?i)(?:https?://)?(?:www\.)?t\.me/(?:addstickers|addemoji)/"
    r"[A-Za-z0-9_]{1,64}(?![A-Za-z0-9_/])"
)


async def _validate_download(
    path: Path,
    settings: Settings,
    *,
    expected: MediaFormat | None = None,
) -> MediaFormat:
    return await validate_source_file(
        path,
        expected=expected,
        max_dimension=settings.max_raster_dimension,
        max_pixels=settings.max_raster_pixels,
        max_tgs_decompressed=settings.max_tgs_json,
    )


def parse_pack_link(value: str) -> tuple[str, str] | None:
    raw = value.strip()
    candidate = raw if "://" in raw else f"https://{raw}"
    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in {"http", "https"} or parsed.hostname not in {"t.me", "www.t.me"}:
        return None
    try:
        unsafe_authority = bool(parsed.username or parsed.password or parsed.port)
    except ValueError:
        return None
    if unsafe_authority:
        return None
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if len(parts) != 2 or parts[0] not in {"addstickers", "addemoji"}:
        return None
    name = parts[1]
    if not name or len(name) > 64 or not name.replace("_", "a").isalnum() or not name.isascii():
        return None
    return parts[0], name


def find_pack_link(value: str) -> tuple[str, str] | None:
    """Find one safe Telegram pack URL inside plain or Markdown-like text."""

    direct = parse_pack_link(value)
    if direct is not None:
        return direct
    for match in PACK_LINK_RE.finditer(value):
        parsed = parse_pack_link(match.group(0))
        if parsed is not None:
            return parsed
    return None


def message_pack_link(message: Message) -> tuple[str, str] | None:
    text = message.text or message.caption or ""
    entities = message.entities if message.text is not None else message.caption_entities
    for entity in entities or []:
        if entity.url:
            parsed = find_pack_link(entity.url)
            if parsed is not None:
                return parsed
        extracted = entity.extract_from(text)
        parsed = find_pack_link(extracted)
        if parsed is not None:
            return parsed
    return find_pack_link(text)


def sticker_format(sticker: Sticker) -> MediaFormat:
    if sticker.is_animated:
        return MediaFormat.TGS
    if sticker.is_video:
        return MediaFormat.WEBM
    return MediaFormat.WEBP


def _source_item(
    sticker: Sticker, path: Path, index: int, preview_path: Path | None = None
) -> SourceItem:
    association = (sticker.emoji,) if sticker.emoji else ("🎨",)
    return SourceItem(
        index=index,
        path=path,
        format=sticker_format(sticker),
        preview_path=preview_path,
        emoji_list=association,
        custom_emoji_id=sticker.custom_emoji_id,
        needs_repainting=bool(sticker.needs_repainting),
    )


async def resolve_pack(
    bot: Bot, job: RuntimeJob, name: str, settings: Settings
) -> SourceDescriptor:
    sticker_set = await bot.get_sticker_set(name)
    if len(sticker_set.stickers) > settings.max_logical_items:
        raise SourceError("Sticker set exceeds the logical item limit")
    items: list[SourceItem] = []
    source_dir = job.root / "source"
    for index, sticker in enumerate(sticker_set.stickers, 1):
        if job.cancel_event.is_set():
            raise asyncio.CancelledError
        error: Exception | None = None
        for _ in range(2):
            try:
                path = await download_sticker(
                    bot, sticker, source_dir, index, settings.max_input_download
                )
                expected = sticker_format(sticker)
                await _validate_download(path, settings, expected=expected)
                preview_path: Path | None = None
                if sticker.thumbnail is not None:
                    try:
                        preview_path = await download_thumbnail(
                            bot,
                            sticker.thumbnail,
                            source_dir,
                            index,
                            settings.max_input_download,
                        )
                    except (OSError, ValueError):
                        preview_path = None
                items.append(_source_item(sticker, path, index, preview_path))
                error = None
                break
            except (OSError, ValueError) as current_error:
                error = current_error
                (source_dir / f"{index:03d}{sticker_extension(sticker)}").unlink(
                    missing_ok=True
                )
        if error is not None:
            job.errors.append((index, _job_error_reason(error)))
    if not items:
        raise SourceError("Sticker set is empty")
    return SourceDescriptor(
        kind=SourceKind.PACK,
        items=items,
        title=sticker_set.title,
        sticker_type=sticker_set.sticker_type,
    )


async def resolve_sticker(
    bot: Bot, job: RuntimeJob, sticker: Sticker, settings: Settings
) -> SourceDescriptor:
    path = await download_sticker(bot, sticker, job.root / "source", 1, settings.max_input_download)
    await _validate_download(path, settings, expected=sticker_format(sticker))
    kind = SourceKind.CUSTOM_EMOJI if sticker.type == "custom_emoji" else SourceKind.STICKER
    preview_path: Path | None = None
    if sticker.thumbnail is not None:
        try:
            preview_path = await download_thumbnail(
                bot,
                sticker.thumbnail,
                job.root / "source",
                1,
                settings.max_input_download,
            )
        except (OSError, ValueError):
            preview_path = None
    return SourceDescriptor(
        kind=kind,
        items=[_source_item(sticker, path, 1, preview_path)],
        title="Custom Emoji" if kind == SourceKind.CUSTOM_EMOJI else "Sticker",
        sticker_type=sticker.type,
    )


async def resolve_custom_emoji_entity(
    bot: Bot, job: RuntimeJob, custom_emoji_id: str, settings: Settings
) -> SourceDescriptor:
    stickers = await bot.get_custom_emoji_stickers([custom_emoji_id])
    if len(stickers) != 1:
        raise SourceError("Telegram did not return the Custom Emoji")
    return await resolve_sticker(bot, job, stickers[0], settings)


async def resolve_custom_emoji_entities(
    bot: Bot,
    job: RuntimeJob,
    custom_emoji_ids: Sequence[str],
    settings: Settings,
) -> SourceDescriptor:
    ordered_ids = list(dict.fromkeys(custom_emoji_ids))
    if len(ordered_ids) > settings.max_logical_items:
        raise SourceError("Too many Custom Emoji in one message")
    stickers = await bot.get_custom_emoji_stickers(ordered_ids)
    by_id = {
        sticker.custom_emoji_id: sticker
        for sticker in stickers
        if sticker.custom_emoji_id is not None
    }
    source_dir = job.root / "source"
    items: list[SourceItem] = []
    for index, custom_emoji_id in enumerate(ordered_ids, 1):
        sticker = by_id.get(custom_emoji_id)
        if sticker is None:
            job.errors.append((index, "Telegram did not return the Custom Emoji"))
            continue
        try:
            path = await download_sticker(
                bot, sticker, source_dir, index, settings.max_input_download
            )
            expected = sticker_format(sticker)
            await _validate_download(path, settings, expected=expected)
            preview_path: Path | None = None
            if sticker.thumbnail is not None:
                try:
                    preview_path = await download_thumbnail(
                        bot,
                        sticker.thumbnail,
                        source_dir,
                        index,
                        settings.max_input_download,
                    )
                except (OSError, ValueError):
                    preview_path = None
            items.append(_source_item(sticker, path, index, preview_path))
        except (OSError, ValueError) as error:
            job.errors.append((index, _job_error_reason(error)))
    if not items:
        raise SourceError("Telegram did not return usable Custom Emoji")
    return SourceDescriptor(
        kind=SourceKind.CUSTOM_EMOJI,
        items=items,
        title="Custom Emoji",
        sticker_type="custom_emoji",
    )


async def resolve_document(
    bot: Bot, job: RuntimeJob, message: Message, settings: Settings
) -> SourceDescriptor:
    if message.document is None:
        raise SourceError("Document is missing")
    path = await download_document(
        bot, message.document, job.root / "source", 1, settings.max_input_download
    )
    actual = await _validate_download(path, settings)
    if path.suffix.lower() == ".zip":
        # ZIP has no short magic branch in detect_format, so direct documents are checked here.
        raise SourceError("ZIP signature was not recognized")
    preview_path: Path | None = None
    if message.document.thumbnail is not None:
        try:
            preview_path = await download_thumbnail(
                bot,
                message.document.thumbnail,
                job.root / "source",
                1,
                settings.max_input_download,
            )
        except (OSError, ValueError):
            preview_path = None
    return SourceDescriptor(
        kind=SourceKind.FILE,
        items=[
            SourceItem(
                index=1,
                path=path,
                format=actual,
                preview_path=preview_path,
                original_name=message.document.file_name,
            )
        ],
        title="File",
    )


async def resolve_zip_document(
    bot: Bot, job: RuntimeJob, message: Message, settings: Settings
) -> SourceDescriptor:
    if message.document is None:
        raise SourceError("Document is missing")
    path = await download_document(
        bot, message.document, job.root / "source", 0, settings.max_input_download
    )
    with path.open("rb") as source:
        signature = source.read(4)
    if signature != b"PK\x03\x04":
        raise SourceError("ZIP signature is invalid")
    extracted = await asyncio.to_thread(
        extract_zip,
        path,
        job.root / "source" / "extracted",
        max_files=settings.max_zip_files,
        max_total_size=settings.max_zip_extracted,
    )
    path.unlink(missing_ok=True)
    items: list[SourceItem] = []
    for index, item in enumerate(extracted, 1):
        actual = await _validate_download(item, settings)
        items.append(
            SourceItem(index=index, path=item, format=actual, original_name=item.name)
        )
    return SourceDescriptor(kind=SourceKind.ZIP, items=items, title="ZIP")


async def resolve_media_group(
    bot: Bot,
    job: RuntimeJob,
    messages: Sequence[Message],
    settings: Settings,
) -> SourceDescriptor:
    if len(messages) > settings.max_media_group_files:
        raise SourceError("Media group contains too many files")
    items: list[SourceItem] = []
    for index, message in enumerate(sorted(messages, key=lambda value: value.message_id), 1):
        if message.document is None:
            raise SourceError("Media groups must contain supported documents")
        try:
            path = await download_document(
                bot, message.document, job.root / "source", index, settings.max_input_download
            )
            preview_path: Path | None = None
            if message.document.thumbnail is not None:
                try:
                    preview_path = await download_thumbnail(
                        bot,
                        message.document.thumbnail,
                        job.root / "source",
                        index,
                        settings.max_input_download,
                    )
                except (OSError, ValueError):
                    preview_path = None
            actual = await _validate_download(path, settings)
            items.append(
                SourceItem(
                    index=index,
                    path=path,
                    format=actual,
                    preview_path=preview_path,
                    original_name=message.document.file_name,
                )
            )
        except (OSError, ValueError) as error:
            job.errors.append((index, _job_error_reason(error)))
    if not items:
        raise SourceError("Media group contains no valid supported files")
    return SourceDescriptor(kind=SourceKind.MEDIA_GROUP, items=items, title="Media group")


async def resolve_message(
    bot: Bot, job: RuntimeJob, message: Message, settings: Settings
) -> SourceDescriptor:
    if message.sticker:
        return await resolve_sticker(bot, job, message.sticker, settings)
    text = (message.text or message.caption or "").strip()
    link = message_pack_link(message)
    if link:
        return await resolve_pack(bot, job, link[1], settings)
    entities = message.entities or message.caption_entities
    if entities:
        custom_ids = [
            entity.custom_emoji_id
            for entity in entities
            if entity.type == MessageEntityType.CUSTOM_EMOJI and entity.custom_emoji_id
        ]
        if custom_ids:
            return await resolve_custom_emoji_entities(bot, job, custom_ids, settings)
    graphemes = extract_emojis(text)
    if graphemes:
        if len(graphemes) > settings.max_logical_items:
            raise SourceError("Too many Unicode Emoji in one message")
        items: list[SourceItem] = []
        for index, grapheme in enumerate(graphemes, 1):
            path = await asyncio.to_thread(
                render_emoji,
                grapheme,
                job.root / "source" / f"{index:03d}.png",
                settings.emoji_font_path,
            )
            await _validate_download(path, settings, expected=MediaFormat.PNG)
            items.append(
                SourceItem(
                    index=index,
                    path=path,
                    format=MediaFormat.PNG,
                    emoji_list=(grapheme,),
                )
            )
        return SourceDescriptor(
            kind=SourceKind.UNICODE,
            items=items,
            title="Unicode Emoji",
        )
    if message.document:
        if (message.document.file_name or "").lower().endswith(".zip"):
            return await resolve_zip_document(bot, job, message, settings)
        return await resolve_document(bot, job, message, settings)
    raise SourceError("Unsupported source")
