"""Strict source identification without arbitrary HTTP fetching."""

from __future__ import annotations

import asyncio
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
from app.services.telegram_files import download_document, download_sticker, sticker_extension
from app.services.unicode_emoji import extract_single_emoji, render_emoji
from app.validators.common import detect_format


class SourceError(ValueError):
    """The Telegram message cannot be resolved into a safe supported source."""


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


def sticker_format(sticker: Sticker) -> MediaFormat:
    if sticker.is_animated:
        return MediaFormat.TGS
    if sticker.is_video:
        return MediaFormat.WEBM
    return MediaFormat.WEBP


def _source_item(sticker: Sticker, path: Path, index: int) -> SourceItem:
    association = (sticker.emoji,) if sticker.emoji else ("🎨",)
    return SourceItem(
        index=index,
        path=path,
        format=sticker_format(sticker),
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
                actual = detect_format(path)
                expected = sticker_format(sticker)
                if actual != expected:
                    raise SourceError(
                        "Telegram sticker content does not match its declared format"
                    )
                items.append(_source_item(sticker, path, index))
                error = None
                break
            except (OSError, ValueError) as current_error:
                error = current_error
                (source_dir / f"{index:03d}{sticker_extension(sticker)}").unlink(
                    missing_ok=True
                )
        if error is not None:
            job.errors.append((index, type(error).__name__))
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
    if detect_format(path) != sticker_format(sticker):
        raise SourceError("Sticker content signature is invalid")
    kind = SourceKind.CUSTOM_EMOJI if sticker.type == "custom_emoji" else SourceKind.STICKER
    return SourceDescriptor(
        kind=kind,
        items=[_source_item(sticker, path, 1)],
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


async def resolve_document(
    bot: Bot, job: RuntimeJob, message: Message, settings: Settings
) -> SourceDescriptor:
    if message.document is None:
        raise SourceError("Document is missing")
    path = await download_document(
        bot, message.document, job.root / "source", 1, settings.max_input_download
    )
    actual = detect_format(path)
    if path.suffix.lower() == ".zip":
        # ZIP has no short magic branch in detect_format, so direct documents are checked here.
        raise SourceError("ZIP signature was not recognized")
    return SourceDescriptor(
        kind=SourceKind.FILE,
        items=[SourceItem(index=1, path=path, format=actual, original_name=message.document.file_name)],
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
    items = [
        SourceItem(index=index, path=item, format=detect_format(item), original_name=item.name)
        for index, item in enumerate(extracted, 1)
    ]
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
            items.append(
                SourceItem(
                    index=index,
                    path=path,
                    format=detect_format(path),
                    original_name=message.document.file_name,
                )
            )
        except (OSError, ValueError) as error:
            job.errors.append((index, type(error).__name__))
    if not items:
        raise SourceError("Media group contains no valid supported files")
    return SourceDescriptor(kind=SourceKind.MEDIA_GROUP, items=items, title="Media group")


async def resolve_message(
    bot: Bot, job: RuntimeJob, message: Message, settings: Settings
) -> SourceDescriptor:
    if message.sticker:
        return await resolve_sticker(bot, job, message.sticker, settings)
    text = (message.text or "").strip()
    link = parse_pack_link(text)
    if link:
        return await resolve_pack(bot, job, link[1], settings)
    if message.entities:
        custom_ids = [
            entity.custom_emoji_id
            for entity in message.entities
            if entity.type == MessageEntityType.CUSTOM_EMOJI and entity.custom_emoji_id
        ]
        if len(custom_ids) == 1:
            return await resolve_custom_emoji_entity(bot, job, custom_ids[0], settings)
    grapheme = extract_single_emoji(text)
    if grapheme:
        path = await asyncio.to_thread(
            render_emoji,
            grapheme,
            job.root / "source" / "001.png",
            settings.emoji_font_path,
        )
        return SourceDescriptor(
            kind=SourceKind.UNICODE,
            items=[SourceItem(index=1, path=path, format=MediaFormat.PNG, emoji_list=(grapheme,))],
            title="Unicode Emoji",
        )
    if message.document:
        if (message.document.file_name or "").lower().endswith(".zip"):
            return await resolve_zip_document(bot, job, message, settings)
        return await resolve_document(bot, job, message, settings)
    raise SourceError("Unsupported source")
