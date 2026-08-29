"""Premium Emoji aware send/edit layer with automatic fallback."""

from __future__ import annotations

import re
from typing import Any

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.services.premium_emoji import PremiumEmojiRegistry

TG_EMOJI_RE = re.compile(r'<tg-emoji\s+emoji-id="\d+">(.*?)</tg-emoji>')


def fallback_html(value: str) -> str:
    return TG_EMOJI_RE.sub(r"\1", value)


def fallback_markup(markup: InlineKeyboardMarkup | None) -> InlineKeyboardMarkup | None:
    if markup is None:
        return None
    rows: list[list[InlineKeyboardButton]] = []
    for row in markup.inline_keyboard:
        rows.append([button.model_copy(update={"icon_custom_emoji_id": None}) for button in row])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def premium_error(error: TelegramBadRequest) -> bool:
    message = str(error).lower()
    return (
        "custom emoji" in message
        or "custom_emoji" in message
        or "emoji-id" in message
        or "tg-emoji" in message
        or "button_type_invalid" in message
    )


def message_not_modified(error: TelegramBadRequest) -> bool:
    return "message is not modified" in str(error).lower()


class SafeUI:
    def __init__(self, registry: PremiumEmojiRegistry) -> None:
        self.registry = registry

    async def answer(
        self,
        message: Message,
        text: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
        **kwargs: Any,
    ) -> Message:
        try:
            return await message.answer(text, reply_markup=reply_markup, **kwargs)
        except TelegramBadRequest as error:
            if not premium_error(error):
                raise
            self.registry.disable()
            return await message.answer(
                fallback_html(text), reply_markup=fallback_markup(reply_markup), **kwargs
            )

    async def edit(
        self,
        message: Message,
        text: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
        retry_as_answer: bool = True,
        **kwargs: Any,
    ) -> Message | bool:
        try:
            return await message.edit_text(text, reply_markup=reply_markup, **kwargs)
        except TelegramRetryAfter:
            # A cosmetic status edit must never abort rendering or pack
            # publication. Important prompts/results are delivered as a fresh
            # message; high-frequency progress updates opt out to avoid spam.
            if not retry_as_answer:
                return message
            return await self.answer(
                message,
                text,
                reply_markup=reply_markup,
                **kwargs,
            )
        except TelegramBadRequest as error:
            if message_not_modified(error):
                return message
            if not premium_error(error):
                raise
            self.registry.disable()
            try:
                return await message.edit_text(
                    fallback_html(text), reply_markup=fallback_markup(reply_markup), **kwargs
                )
            except TelegramBadRequest as fallback_error:
                if message_not_modified(fallback_error):
                    return message
                raise
