"""Minimal user keyboards with centralized Premium Emoji button icons."""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.premium_emoji import PremiumEmojiRegistry

BUTTON_LABELS = {
    "ru": {
        "adaptive": "Сделать Adaptive",
        "cancel": "Отмена",
        "continue": "Продолжить",
        "recolor": "Другой цвет",
        "emoji_pack": "Эмодзи-пак",
        "sticker_pack": "Стикер-пак",
        "file": "Файл",
        "zip": "ZIP-архив",
        "add_pack": "Добавить набор",
        "restart": "Перекрасить ещё",
        "source_title": "Использовать название исходного",
        "split": "Разделить",
        "main_recolor": "Покрасить эмодзи",
        "my_packs": "Мои наборы",
        "information": "Информация",
        "open_stickers": "Открыть @Stickers",
        "back": "Назад",
    },
    "en": {
        "adaptive": "Make Adaptive",
        "cancel": "Cancel",
        "continue": "Continue",
        "recolor": "Another color",
        "emoji_pack": "Emoji Pack",
        "sticker_pack": "Sticker Pack",
        "file": "File",
        "zip": "ZIP archive",
        "add_pack": "Add pack",
        "restart": "Recolor another",
        "source_title": "Use source title",
        "split": "Split",
        "main_recolor": "Recolor Emoji",
        "my_packs": "My packs",
        "information": "Information",
        "open_stickers": "Open @Stickers",
        "back": "Back",
    },
}


def _label(language: str, key: str) -> str:
    return BUTTON_LABELS.get(language, BUTTON_LABELS["en"])[key]


def _button(
    registry: PremiumEmojiRegistry,
    icon: str,
    text: str,
    **action: Any,
) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        icon_custom_emoji_id=registry.button_id(icon),
        **action,
    )


def language_keyboard(registry: PremiumEmojiRegistry) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button(registry, "FLAG_RU", "Русский", callback_data="lang:ru")],
            [_button(registry, "FLAG_EN", "English", callback_data="lang:en")],
        ]
    )


def main_menu_keyboard(
    registry: PremiumEmojiRegistry, language: str = "en"
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button(
                    registry,
                    "BRUSH",
                    _label(language, "main_recolor"),
                    callback_data="menu:recolor",
                    style="primary",
                )
            ],
            [
                _button(
                    registry,
                    "PACK",
                    _label(language, "my_packs"),
                    callback_data="menu:packs",
                )
            ],
            [
                _button(
                    registry,
                    "INFO",
                    _label(language, "information"),
                    callback_data="menu:info",
                )
            ],
        ]
    )


def menu_back_keyboard(
    registry: PremiumEmojiRegistry, language: str = "en"
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button(
                    registry,
                    "BACK",
                    _label(language, "back"),
                    callback_data="menu:home",
                )
            ]
        ]
    )


def packs_keyboard(
    registry: PremiumEmojiRegistry, language: str = "en"
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button(
                    registry,
                    "PACK",
                    _label(language, "open_stickers"),
                    url="https://t.me/Stickers",
                )
            ],
            [
                _button(
                    registry,
                    "BACK",
                    _label(language, "back"),
                    callback_data="menu:home",
                )
            ],
        ]
    )


def color_keyboard(
    registry: PremiumEmojiRegistry,
    job_id: str,
    *,
    adaptive: bool = True,
    language: str = "en",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if adaptive:
        rows.append(
            [
                _button(
                    registry,
                    "MAGIC",
                    _label(language, "adaptive"),
                    callback_data=f"job:{job_id}:adaptive",
                )
            ]
        )
    rows.append(
        [
            _button(
                registry,
                "CANCEL",
                _label(language, "cancel"),
                callback_data=f"job:{job_id}:cancel",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def processing_keyboard(
    registry: PremiumEmojiRegistry, job_id: str, language: str = "en"
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button(
                    registry,
                    "CANCEL",
                    _label(language, "cancel"),
                    callback_data=f"job:{job_id}:cancel",
                    style="danger",
                )
            ]
        ]
    )


def preview_keyboard(
    registry: PremiumEmojiRegistry, job_id: str, language: str = "en"
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button(registry, "SUCCESS", _label(language, "continue"), callback_data=f"job:{job_id}:continue")],
            [_button(registry, "EDIT", _label(language, "recolor"), callback_data=f"job:{job_id}:recolor")],
            [_button(registry, "CANCEL", _label(language, "cancel"), callback_data=f"job:{job_id}:cancel")],
        ]
    )


def adaptive_preview_keyboard(
    registry: PremiumEmojiRegistry, job_id: str, language: str = "en"
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button(registry, "SUCCESS", _label(language, "continue"), callback_data=f"job:{job_id}:adaptive_ok")],
            [_button(registry, "CANCEL", _label(language, "cancel"), callback_data=f"job:{job_id}:cancel")],
        ]
    )


def output_keyboard(
    registry: PremiumEmojiRegistry, job_id: str, *, single: bool, language: str = "en"
) -> InlineKeyboardMarkup:
    rows = [
        [_button(registry, "EMOJI", _label(language, "emoji_pack"), callback_data=f"job:{job_id}:out:emoji_pack")],
        [_button(registry, "STICKER", _label(language, "sticker_pack"), callback_data=f"job:{job_id}:out:sticker_pack")],
    ]
    if single:
        rows.append([_button(registry, "FILE", _label(language, "file"), callback_data=f"job:{job_id}:out:file")])
    rows.extend(
        [
            [_button(registry, "ZIP", _label(language, "zip"), callback_data=f"job:{job_id}:out:zip")],
            [_button(registry, "CANCEL", _label(language, "cancel"), callback_data=f"job:{job_id}:cancel")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def result_keyboard(
    registry: PremiumEmojiRegistry, *, add_url: str | None = None, language: str = "en"
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if add_url:
        rows.append([_button(registry, "ADD", _label(language, "add_pack"), url=add_url)])
    rows.append([_button(registry, "BRUSH", _label(language, "restart"), callback_data="restart")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pack_name_keyboard(
    registry: PremiumEmojiRegistry, job_id: str, *, source_title: bool, language: str = "en"
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if source_title:
        rows.append(
            [
                _button(
                    registry,
                    "PACK",
                    _label(language, "source_title"),
                    callback_data=f"job:{job_id}:source_title",
                )
            ]
        )
    rows.append([_button(registry, "CANCEL", _label(language, "cancel"), callback_data=f"job:{job_id}:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def split_keyboard(
    registry: PremiumEmojiRegistry, job_id: str, language: str = "en"
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button(registry, "SUCCESS", _label(language, "split"), callback_data=f"job:{job_id}:split")],
            [_button(registry, "CANCEL", _label(language, "cancel"), callback_data=f"job:{job_id}:cancel")],
        ]
    )
