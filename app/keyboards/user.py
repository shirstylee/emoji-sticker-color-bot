"""Minimal user keyboards with centralized Premium Emoji button icons."""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.models.job import RecolorIntensity
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
        "download_file": "Скачать файл",
        "add_emoji_pack": "Добавить в Emoji-набор",
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
        "support": "Техническая поддержка",
        "home": "Главное меню",
        "existing_pack": "Добавить в существующий набор",
        "enter_pack_link": "Вставить ссылку",
        "intensity_soft": "Бережная",
        "intensity_normal": "Обычная",
        "intensity_vivid": "Насыщенная",
        "cancel_last": "Отменить последнюю задачу",
        "cancel_all": "Отменить все задачи",
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
        "download_file": "Download file",
        "add_emoji_pack": "Add to Emoji Pack",
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
        "support": "Technical support",
        "home": "Main menu",
        "existing_pack": "Add to existing pack",
        "enter_pack_link": "Paste a link",
        "intensity_soft": "Soft",
        "intensity_normal": "Normal",
        "intensity_vivid": "Vivid",
        "cancel_last": "Cancel latest job",
        "cancel_all": "Cancel all jobs",
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
            [
                _button(registry, "FLAG_RU", "Русский", callback_data="lang:ru"),
                _button(registry, "FLAG_EN", "English", callback_data="lang:en"),
            ],
        ]
    )


def main_menu_keyboard(
    registry: PremiumEmojiRegistry,
    language: str = "ru",
    *,
    is_admin: bool = False,
) -> InlineKeyboardMarkup:
    rows = [
        [
            _button(
                registry,
                "BRUSH",
                _label(language, "main_recolor"),
                callback_data="menu:recolor",
                style="primary",
            )
        ],
    ]
    if is_admin:
        rows.append(
            [
                _button(
                    registry,
                    "PACK",
                    _label(language, "my_packs"),
                    callback_data="menu:packs",
                )
            ]
        )
    rows.append(
        [
            _button(
                registry,
                "INFO",
                _label(language, "information"),
                callback_data="menu:info",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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


def information_keyboard(
    registry: PremiumEmojiRegistry, language: str = "en"
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button(
                    registry,
                    "SUPPORT",
                    _label(language, "support"),
                    url="https://t.me/ragedick",
                    style="primary",
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
    color_picker_url: str,
    *,
    adaptive: bool = True,
    language: str = "en",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            _button(
                registry,
                "COLOR",
                _label(language, "picker"),
                web_app=WebAppInfo(url=color_picker_url),
            )
        ]
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


def cancel_jobs_keyboard(
    registry: PremiumEmojiRegistry, language: str = "en"
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button(
                    registry,
                    "CANCEL",
                    _label(language, "cancel_last"),
                    callback_data="cancel:last",
                    style="danger",
                )
            ],
            [
                _button(
                    registry,
                    "DELETE",
                    _label(language, "cancel_all"),
                    callback_data="cancel:all",
                    style="danger",
                )
            ],
        ]
    )


def _intensity_row(
    registry: PremiumEmojiRegistry,
    job_id: str,
    language: str,
    selected: RecolorIntensity,
) -> list[InlineKeyboardButton]:
    return [
        _button(
            registry,
            "COLOR",
            _label(language, f"intensity_{value.value}"),
            callback_data=f"job:{job_id}:intensity:{value.value}",
            style="primary" if value == selected else None,
        )
        for value in RecolorIntensity
    ]


def preview_keyboard(
    registry: PremiumEmojiRegistry,
    job_id: str,
    language: str = "en",
    intensity: RecolorIntensity = RecolorIntensity.NORMAL,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button(registry, "SUCCESS", _label(language, "continue"), callback_data=f"job:{job_id}:continue")],
            _intensity_row(registry, job_id, language, intensity),
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
            [_button(registry, "ADD", _label(language, "existing_pack"), callback_data=f"job:{job_id}:existing")],
            [_button(registry, "CANCEL", _label(language, "cancel"), callback_data=f"job:{job_id}:cancel")],
        ]
    )


def output_keyboard(
    registry: PremiumEmojiRegistry, job_id: str, *, single: bool, language: str = "en"
) -> InlineKeyboardMarkup:
    rows = [
        [_button(registry, "EMOJI", _label(language, "emoji_pack"), callback_data=f"job:{job_id}:out:emoji_pack")],
        [_button(registry, "STICKER", _label(language, "sticker_pack"), callback_data=f"job:{job_id}:out:sticker_pack")],
        [_button(registry, "ADD", _label(language, "existing_pack"), callback_data=f"job:{job_id}:existing")],
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
    rows.append(
        [_button(registry, "HOME", _label(language, "home"), callback_data="menu:home")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def single_result_keyboard(
    registry: PremiumEmojiRegistry,
    job_id: str,
    language: str = "en",
    intensity: RecolorIntensity = RecolorIntensity.NORMAL,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button(
                    registry,
                    "EMOJI",
                    _label(language, "add_emoji_pack"),
                    callback_data=f"job:{job_id}:single_pack",
                    style="primary",
                )
            ],
            [
                _button(
                    registry,
                    "ADD",
                    _label(language, "existing_pack"),
                    callback_data=f"job:{job_id}:existing",
                )
            ],
            _intensity_row(registry, job_id, language, intensity),
            [
                _button(
                    registry,
                    "BRUSH",
                    _label(language, "restart"),
                    callback_data=f"job:{job_id}:restart",
                )
            ],
            [
                _button(
                    registry,
                    "HOME",
                    _label(language, "home"),
                    callback_data=f"job:{job_id}:home",
                )
            ],
        ]
    )


def existing_pack_keyboard(
    registry: PremiumEmojiRegistry,
    job_id: str,
    packs: list[dict[str, str]],
    language: str = "en",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index, pack in enumerate(packs):
        title = pack.get("title") or pack.get("url") or "Pack"
        rows.append(
            [
                _button(
                    registry,
                    "PACK",
                    title[:48],
                    callback_data=f"job:{job_id}:existing_saved:{index}",
                )
            ]
        )
    rows.extend(
        [
            [
                _button(
                    registry,
                    "LINK",
                    _label(language, "enter_pack_link"),
                    callback_data=f"job:{job_id}:existing_link",
                )
            ],
            [
                _button(
                    registry,
                    "BACK",
                    _label(language, "back"),
                    callback_data=f"job:{job_id}:pack_back",
                )
            ],
            [
                _button(
                    registry,
                    "CANCEL",
                    _label(language, "cancel"),
                    callback_data=f"job:{job_id}:cancel",
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pack_name_keyboard(
    registry: PremiumEmojiRegistry,
    job_id: str,
    *,
    source_title: bool,
    language: str = "en",
    back_action: str = "pack_back",
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
    rows.extend(
        [
            [
                _button(
                    registry,
                    "BACK",
                    _label(language, "back"),
                    callback_data=f"job:{job_id}:{back_action}",
                )
            ],
            [
                _button(
                    registry,
                    "CANCEL",
                    _label(language, "cancel"),
                    callback_data=f"job:{job_id}:cancel",
                )
            ],
        ]
    )
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
