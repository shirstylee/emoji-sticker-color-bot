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
from aiogram.types import FSInputFile, InputSticker, Message
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


def input_sticker(
    sticker: Path | str,
    media_format: MediaFormat,
    emoji_list: Sequence[str],
) -> InputSticker:
    return InputSticker(
        sticker=FSInputFile(sticker) if isinstance(sticker, Path) else sticker,
        format=telegram_sticker_format(media_format),
        emoji_list=list(emoji_list)[:20] or ["🎨"],
    )


def _wrong_file_type(error: TelegramBadRequest) -> bool:
    message = str(error).lower()
    return "wrong file type" in message or "sticker_file_invalid" in message


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
        on_progress: Callable[[int, int], Awaitable[None]] | None = None,
        on_prepare: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> str:
        maximum = TELEGRAM_CUSTOM_EMOJI_SET_MAX if custom_emoji else TELEGRAM_REGULAR_STICKER_SET_MAX
        if not files or len(files) > maximum:
            raise ValueError("Sticker set item count is outside Telegram limits")
        for attempt in range(6):
            name = generate_short_name(title, bot_username)
            initial_files = files[:TELEGRAM_CREATE_INITIAL_MAX]
            initial: list[InputSticker] = []
            for prepared, item in enumerate(initial_files, 1):
                initial.append(
                    await self._prepare_input_sticker(
                        user_id,
                        item,
                        cancel_event,
                        on_flood,
                    )
                )
                if on_prepare:
                    await on_prepare(prepared, len(files))
            create_state = [initial]

            async def create(
                name: str = name,
                create_state: list[list[InputSticker]] = create_state,
            ) -> bool:
                return await self.bot.create_new_sticker_set(
                    user_id=user_id,
                    name=name,
                    title=title,
                    stickers=create_state[0],
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
                if not _wrong_file_type(error):
                    raise
                initial = [
                    input_sticker(
                        await self._upload_file(
                            user_id,
                            path,
                            media_format,
                            cancel_event,
                            on_flood,
                        ),
                        media_format,
                        emoji_list,
                    )
                    for path, media_format, emoji_list in initial_files
                ]
                create_state[0] = initial
                await self.controller.call(create, cancel_event, on_flood=on_flood)
            completed = len(initial_files)
            if on_progress:
                await on_progress(completed, len(files))
            try:
                for item in files[TELEGRAM_CREATE_INITIAL_MAX:]:
                    sticker = await self._prepare_input_sticker(
                        user_id,
                        item,
                        cancel_event,
                        on_flood,
                    )
                    if on_prepare:
                        await on_prepare(completed + 1, len(files))
                    add_state = [sticker]

                    async def add(
                        name: str = name,
                        add_state: list[InputSticker] = add_state,
                    ) -> bool:
                        return await self.bot.add_sticker_to_set(
                            user_id=user_id, name=name, sticker=add_state[0]
                        )

                    try:
                        await self.controller.call(add, cancel_event, on_flood=on_flood)
                    except TelegramBadRequest as error:
                        if not _wrong_file_type(error):
                            raise
                        path, media_format, emoji_list = item
                        sticker = input_sticker(
                            await self._upload_file(
                                user_id,
                                path,
                                media_format,
                                cancel_event,
                                on_flood,
                            ),
                            media_format,
                            emoji_list,
                        )
                        add_state[0] = sticker
                        await self.controller.call(add, cancel_event, on_flood=on_flood)
                    completed += 1
                    if on_progress:
                        await on_progress(completed, len(files))
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

    async def _prepare_input_sticker(
        self,
        user_id: int,
        item: tuple[Path, MediaFormat, Sequence[str]],
        cancel_event: asyncio.Event,
        on_flood: Callable[[float], Awaitable[None]] | None,
    ) -> InputSticker:
        path, media_format, emoji_list = item
        # Telegram explicitly requires uploadStickerFile before a TGS sticker
        # is shown. Pre-uploading also prevents Telegram from classifying a
        # valid animation as a generic document ("Unknown Track").
        sticker: Path | str = path
        if media_format == MediaFormat.TGS:
            sticker = await self._upload_file(
                user_id,
                path,
                media_format,
                cancel_event,
                on_flood,
            )
        return input_sticker(sticker, media_format, emoji_list)

    async def _upload_file(
        self,
        user_id: int,
        path: Path,
        media_format: MediaFormat,
        cancel_event: asyncio.Event,
        on_flood: Callable[[float], Awaitable[None]] | None,
    ) -> str:
        async def upload() -> object:
            return await self.bot.upload_sticker_file(
                user_id=user_id,
                sticker=FSInputFile(path, filename=f"sticker{path.suffix.lower()}"),
                sticker_format=telegram_sticker_format(media_format),
            )

        uploaded = await self.controller.call(upload, cancel_event, on_flood=on_flood)
        file_id = getattr(uploaded, "file_id", None)
        if not isinstance(file_id, str) or not file_id:
            raise RuntimeError("Telegram did not return an uploaded sticker file_id")
        return file_id

    async def send_sticker_file(
        self,
        *,
        user_id: int,
        chat_id: int,
        path: Path,
        media_format: MediaFormat,
        cancel_event: asyncio.Event,
        on_flood: Callable[[float], Awaitable[None]] | None = None,
    ) -> Message:
        """Send a processed asset as a sticker, uploading it first when required."""

        async def send(sticker: FSInputFile | str) -> Message:
            return await self.bot.send_sticker(chat_id=chat_id, sticker=sticker)

        if media_format == MediaFormat.TGS:
            file_id = await self._upload_file(
                user_id,
                path,
                media_format,
                cancel_event,
                on_flood,
            )
            return await self.controller.call(
                lambda: send(file_id),
                cancel_event,
                on_flood=on_flood,
            )
        try:
            return await self.controller.call(
                lambda: send(FSInputFile(path, filename=f"sticker{path.suffix.lower()}")),
                cancel_event,
                on_flood=on_flood,
            )
        except TelegramBadRequest as error:
            if not _wrong_file_type(error):
                raise
        file_id = await self._upload_file(
            user_id,
            path,
            media_format,
            cancel_event,
            on_flood,
        )
        return await self.controller.call(
            lambda: send(file_id),
            cancel_event,
            on_flood=on_flood,
        )

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
