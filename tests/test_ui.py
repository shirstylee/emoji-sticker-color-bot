from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageText

from app.i18n.en import EN
from app.i18n.ru import RU
from app.keyboards.user import (
    color_keyboard,
    language_keyboard,
    main_menu_keyboard,
    processing_keyboard,
)
from app.main import COMMANDS_EN, COMMANDS_RU
from app.services.premium_emoji import PremiumEmojiRegistry
from app.services.ui import SafeUI


@pytest.fixture
def registry() -> PremiumEmojiRegistry:
    return PremiumEmojiRegistry.load(Path("Main.txt"))


def test_language_keyboard_uses_real_flag_ids(registry: PremiumEmojiRegistry) -> None:
    keyboard = language_keyboard(registry)
    assert keyboard.inline_keyboard[0][0].icon_custom_emoji_id == "5449408995691341691"
    assert keyboard.inline_keyboard[1][0].icon_custom_emoji_id == "5202021044105257611"


def test_main_menu_has_exactly_three_actions_and_blue_primary(
    registry: PremiumEmojiRegistry,
) -> None:
    keyboard = main_menu_keyboard(registry, "ru")
    buttons = [row[0] for row in keyboard.inline_keyboard]
    assert [button.text for button in buttons] == [
        "Покрасить эмодзи",
        "Мои наборы",
        "Информация",
    ]
    assert buttons[0].style == "primary"


def test_color_presets_are_removed_but_cancel_remains(
    registry: PremiumEmojiRegistry,
) -> None:
    keyboard = color_keyboard(registry, "job", language="ru")
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert not any(":color:" in callback for callback in callbacks)
    assert callbacks == ["job:job:adaptive", "job:job:cancel"]

    processing = processing_keyboard(registry, "job", "ru")
    cancel = processing.inline_keyboard[0][0]
    assert cancel.callback_data == "job:job:cancel"
    assert cancel.style == "danger"


def test_color_codes_are_copyable_code_entities() -> None:
    for catalog in (RU, EN):
        assert "<code>#FFFFFF</code>" in catalog["colors"]
        assert "<code>#2196F3</code>" in catalog["source_found"]
        assert "<code>{color}</code>" in catalog["done_file"]


def test_bot_commands_are_localized_without_slash_labels() -> None:
    assert [command.description for command in COMMANDS_RU] == [
        "Начать",
        "Помощь",
        "Цвета",
        "Язык",
        "Отмена",
    ]
    assert [command.description for command in COMMANDS_EN] == [
        "Start",
        "Help",
        "Colors",
        "Language",
        "Cancel",
    ]


@pytest.mark.asyncio
async def test_identical_edit_is_a_benign_noop(registry: PremiumEmojiRegistry) -> None:
    error = TelegramBadRequest(
        method=EditMessageText(chat_id=1, message_id=1, text="same"),
        message="Bad Request: message is not modified",
    )
    message = SimpleNamespace(edit_text=AsyncMock(side_effect=error))
    ui = SafeUI(registry)
    result = await ui.edit(message, "same")  # type: ignore[arg-type]
    assert result is message
    message.edit_text.assert_awaited_once()
