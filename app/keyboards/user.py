"""Minimal user keyboards with centralized Premium Emoji button icons."""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.services.premium_emoji import PremiumEmojiRegistry

BUTTON_LABELS = {
    "ru": {
        "picker": "Подобрать цвет",
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
    },
    "en": {
        "picker": "Pick a color",
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
            [_button(registry, "LANGUAGE", "Русский", callback_data="lang:ru")],
            [_button(registry, "LANGUAGE", "English", callback_data="lang:en")],
        ]
    )


def color_keyboard(
    registry: PremiumEmojiRegistry,
    job_id: str,
    color_picker_url: str,
    *,
    adaptive: bool = True,
    language: str = "en",
) -> InlineKeyboardMarkup:
    rows = [
        [
            _button(registry, "COLOR", "#FFFFFF", callback_data=f"job:{job_id}:color:FFFFFF"),
            _button(registry, "COLOR", "#000000", callback_data=f"job:{job_id}:color:000000"),
        ],
        [
            _button(registry, "COLOR", "#FF0000", callback_data=f"job:{job_id}:color:FF0000"),
            _button(registry, "COLOR", "#2196F3", callback_data=f"job:{job_id}:color:2196F3"),
        ],
        [
            _button(
                registry,
                "COLOR",
                _label(language, "picker"),
                web_app=WebAppInfo(url=color_picker_url),
            )
        ],
    ]
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
