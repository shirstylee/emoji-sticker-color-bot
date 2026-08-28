"""Bounded Telegram downloads into a random job directory."""

from __future__ import annotations

from pathlib import Path

from aiogram import Bot
from aiogram.types import Document, PhotoSize, Sticker


class TelegramFileError(ValueError):
    """Telegram file download failed a size or integrity check."""


def sticker_extension(sticker: Sticker) -> str:
    if sticker.is_animated:
        return ".tgs"
    if sticker.is_video:
        return ".webm"
    return ".webp"


async def download_telegram_file(
    bot: Bot,
    *,
    file_id: str,
    destination: Path,
    declared_size: int | None,
    maximum_bytes: int,
) -> Path:
    if declared_size is not None and declared_size > maximum_bytes:
        raise TelegramFileError("Telegram file exceeds the download limit")
    remote = await bot.get_file(file_id)
    if remote.file_size is not None and remote.file_size > maximum_bytes:
        raise TelegramFileError("Telegram file exceeds the download limit")
    destination.parent.mkdir(parents=True, exist_ok=True)
    await bot.download(remote, destination=destination, timeout=60)
    if not destination.is_file() or destination.stat().st_size > maximum_bytes:
        destination.unlink(missing_ok=True)
        raise TelegramFileError("Downloaded file is missing or too large")
    return destination


async def download_sticker(
    bot: Bot, sticker: Sticker, destination_dir: Path, index: int, maximum_bytes: int
) -> Path:
    return await download_telegram_file(
        bot,
        file_id=sticker.file_id,
        destination=destination_dir / f"{index:03d}{sticker_extension(sticker)}",
        declared_size=sticker.file_size,
        maximum_bytes=maximum_bytes,
    )


async def download_thumbnail(
    bot: Bot, thumbnail: PhotoSize, destination_dir: Path, index: int, maximum_bytes: int
) -> Path:
    return await download_telegram_file(
        bot,
        file_id=thumbnail.file_id,
        destination=destination_dir / f"{index:03d}_preview.jpg",
        declared_size=thumbnail.file_size,
        maximum_bytes=maximum_bytes,
    )


async def download_document(
    bot: Bot, document: Document, destination_dir: Path, index: int, maximum_bytes: int
) -> Path:
    suffix = Path(document.file_name or "file").suffix.lower()[:10]
    return await download_telegram_file(
        bot,
        file_id=document.file_id,
        destination=destination_dir / f"{index:03d}{suffix}",
        declared_size=document.file_size,
        maximum_bytes=maximum_bytes,
    )
