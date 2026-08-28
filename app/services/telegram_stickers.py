"""Efficient Telegram pack publishing with batching, splitting and flood recovery."""

from __future__ import annotations

import asyncio
import contextlib
import re
import secrets
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile, InputSticker
from slugify import slugify

from app.constants import (
    TELEGRAM_CREATE_INITIAL_MAX,
    TELEGRAM_CUSTOM_EMOJI_SET_MAX,
    TELEGRAM_REGULAR_STICKER_SET_MAX,
    TELEGRAM_SHORT_NAME_MAX,
)
from app.models.source import MediaFormat
from app.services.telegram_rate_limiter import TelegramStickerRateController

SHORT_NAME_RE = re.compile(r"[^A-Za-z0-9_]+")


def generate_short_name(
    title: str,
    bot_username: str,
    *,
    token_factory: Callable[[], str] = lambda: secrets.token_hex(3),
) -> str:
    username = SHORT_NAME_RE.sub("", bot_username.lstrip("@"))
    if not username:
        raise ValueError("Bot username is unavailable")
    suffix = f"_by_{username}"
    random_part = SHORT_NAME_RE.sub("", token_factory())[:12] or "color"
    stem = slugify(title, separator="_", lowercase=True, max_length=40)
    stem = re.sub(r"_+", "_", SHORT_NAME_RE.sub("_", stem)).strip("_")
    if not stem or not stem[0].isalpha():
        stem = f"pack_{stem}".strip("_")
    maximum_stem = TELEGRAM_SHORT_NAME_MAX - len(suffix) - len(random_part) - 1
    if maximum_stem < 1:
        raise ValueError("Bot username is too long for a sticker set short name")
    stem = stem[:maximum_stem].rstrip("_") or "p"
    result = re.sub(r"_+", "_", f"{stem}_{random_part}{suffix}")
    if not result[0].isalpha() or len(result) > TELEGRAM_SHORT_NAME_MAX:
        raise ValueError("Could not generate a valid Telegram short name")
    return result


def telegram_sticker_format(media_format: MediaFormat) -> str:
    if media_format == MediaFormat.TGS:
        return "animated"
    if media_format == MediaFormat.WEBM:
        return "video"
    return "static"


def input_sticker(path: Path, media_format: MediaFormat, emoji_list: Sequence[str]) -> InputSticker:
    return InputSticker(
        sticker=FSInputFile(path),
        format=telegram_sticker_format(media_format),
        emoji_list=list(emoji_list)[:20] or ["🎨"],
    )


class StickerPublisher:
    def __init__(self, bot: Bot, controller: TelegramStickerRateController) -> None:
        self.bot = bot
        self.controller = controller

    async def publish_set(
        self,
        *,
        user_id: int,
        title: str,
        bot_username: str,
        files: Sequence[tuple[Path, MediaFormat, Sequence[str]]],
        custom_emoji: bool,
        needs_repainting: bool,
        cancel_event: asyncio.Event,
        on_flood: Callable[[float], Awaitable[None]] | None = None,
    ) -> str:
        maximum = TELEGRAM_CUSTOM_EMOJI_SET_MAX if custom_emoji else TELEGRAM_REGULAR_STICKER_SET_MAX
        if not files or len(files) > maximum:
            raise ValueError("Sticker set item count is outside Telegram limits")
        for attempt in range(6):
            name = generate_short_name(title, bot_username)
            initial = [input_sticker(*item) for item in files[:TELEGRAM_CREATE_INITIAL_MAX]]

            async def create(
                name: str = name, initial: list[InputSticker] = initial
            ) -> bool:
                return await self.bot.create_new_sticker_set(
                    user_id=user_id,
                    name=name,
                    title=title,
                    stickers=initial,
                    sticker_type="custom_emoji" if custom_emoji else "regular",
                    needs_repainting=needs_repainting if custom_emoji else None,
                )

            try:
                await self.controller.call(create, cancel_event, on_flood=on_flood)
            except TelegramBadRequest as error:
                message = str(error).lower()
                if attempt < 5 and (
                    "occupied" in message or ("name" in message and "taken" in message)
                ):
                    continue
                raise
            try:
                for item in files[TELEGRAM_CREATE_INITIAL_MAX:]:
                    sticker = input_sticker(*item)

                    async def add(
                        sticker: InputSticker = sticker, name: str = name
                    ) -> bool:
                        return await self.bot.add_sticker_to_set(
                            user_id=user_id, name=name, sticker=sticker
                        )

                    await self.controller.call(add, cancel_event, on_flood=on_flood)
            except BaseException:
                with contextlib.suppress(Exception):
                    await self.bot.delete_sticker_set(name)
                raise
            if custom_emoji:
                await self._set_custom_thumbnail(name)
            else:
                await self._set_regular_thumbnail(name, user_id, files[0])
            return name
        raise RuntimeError("Could not allocate a Telegram sticker set short name")

    async def _set_custom_thumbnail(self, name: str) -> None:
        try:
            sticker_set = await self.bot.get_sticker_set(name)
            first = sticker_set.stickers[0] if sticker_set.stickers else None
            if first and first.custom_emoji_id:
                await self.bot.set_custom_emoji_sticker_set_thumbnail(
                    name=name, custom_emoji_id=first.custom_emoji_id
                )
        except Exception:
            return

    async def _set_regular_thumbnail(
        self,
        name: str,
        user_id: int,
        first: tuple[Path, MediaFormat, Sequence[str]],
    ) -> None:
        path, media_format, _ = first
        try:
            await self.bot.set_sticker_set_thumbnail(
                name=name,
                user_id=user_id,
                format=telegram_sticker_format(media_format),
                thumbnail=FSInputFile(path),
            )
        except Exception:
            return

    async def delete_sets(self, names: Sequence[str]) -> list[str]:
        failed: list[str] = []
        for name in names:
            try:
                await self.bot.delete_sticker_set(name)
            except Exception:
                failed.append(name)
        return failed


def pack_url(name: str, *, custom_emoji: bool) -> str:
    route = "addemoji" if custom_emoji else "addstickers"
    return f"https://t.me/{route}/{name}"
