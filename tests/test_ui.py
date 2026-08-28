from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageText

from app.i18n.en import EN
from app.i18n.ru import RU
from app.keyboards.admin import admin_keyboard
from app.keyboards.user import (
    color_keyboard,
    language_keyboard,
    main_menu_keyboard,
    processing_keyboard,
)
from app.main import (
    ADMIN_COMMANDS_EN,
    ADMIN_COMMANDS_RU,
    COMMANDS_RU,
    configure_bot_commands,
)
from app.services.premium_emoji import PremiumEmojiRegistry
from app.services.ui import SafeUI


@pytest.fixture
def registry() -> PremiumEmojiRegistry:
    return PremiumEmojiRegistry.load(Path("Main.txt"))


def test_language_keyboard_uses_real_flag_ids(registry: PremiumEmojiRegistry) -> None:
    keyboard = language_keyboard(registry)
    assert len(keyboard.inline_keyboard) == 1
    assert keyboard.inline_keyboard[0][0].icon_custom_emoji_id == "5449408995691341691"
    assert keyboard.inline_keyboard[0][1].icon_custom_emoji_id == "5202021044105257611"


def test_main_menu_has_exactly_three_actions_and_blue_primary(
    registry: PremiumEmojiRegistry,
) -> None:
    keyboard = main_menu_keyboard(registry, "ru", is_admin=True)
    buttons = [row[0] for row in keyboard.inline_keyboard]
    assert [button.text for button in buttons] == [
        "Покрасить эмодзи",
        "Мои наборы",
        "Информация",
    ]
    assert buttons[0].style == "primary"

    regular = main_menu_keyboard(registry, "ru", is_admin=False)
    assert [row[0].text for row in regular.inline_keyboard] == [
        "Покрасить эмодзи",
        "Информация",
    ]


def test_color_presets_are_removed_but_cancel_remains(
    registry: PremiumEmojiRegistry,
) -> None:
    keyboard = color_keyboard(
        registry,
        "job",
        "https://htmlcolorcodes.com/color-picker/",
        language="ru",
    )
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert not any(":color:" in callback for callback in callbacks)
    assert callbacks == ["job:job:adaptive", "job:job:cancel"]
    picker = keyboard.inline_keyboard[0][0]
    assert picker.text == "Подобрать цвет"
    assert picker.web_app is not None
    assert str(picker.web_app.url) == "https://htmlcolorcodes.com/color-picker/"

    processing = processing_keyboard(registry, "job", "ru")
    cancel = processing.inline_keyboard[0][0]
    assert cancel.callback_data == "job:job:cancel"
    assert cancel.style == "danger"


def test_color_codes_are_copyable_code_entities() -> None:
    for catalog in (RU, EN):
        assert "<code>#FFFFFF</code>" in catalog["colors"]
        assert "<code>#2196F3</code>" in catalog["source_found"]
        assert "<code>{color}</code>" in catalog["done_file"]


def test_rich_messages_render_with_real_premium_emoji(
    registry: PremiumEmojiRegistry,
) -> None:
    values: dict[str, object] = {
        "icon": registry.html("BRUSH"),
        "title": "Example",
        "kind": "TGS",
        "count": 1,
        "formats": "TGS: 1",
        "color": "#2196F3",
        "pack_list": "Example pack",
        **registry.placeholders(),
    }
    expected_icon_counts = {
        "main_menu": 3,
        "send_source": 5,
        "my_packs": 2,
        "information": 3,
        "source_found": 6,
        "choose_output": 2,
        "preview_ready": 2,
        "publishing": 2,
        "done_file": 2,
        "done_pack": 5,
    }
    for catalog in (RU, EN):
        for key, expected_count in expected_icon_counts.items():
            rendered = catalog[key].format(**values)
            assert "{" not in rendered
            assert rendered.count("<tg-emoji ") == expected_count

    assert "Отправьте материал для перекраски" in RU["send_source"]
    assert not RU["send_source"].startswith("<blockquote>")
    assert "\n\n<blockquote>{emoji_icon}" in RU["send_source"]
    assert RU["send_source"].endswith("</blockquote>")
    assert "Premium Emoji — отдельным сообщением" in RU["send_source"]
    assert "Стикер — отдельным сообщением" in RU["send_source"]


def test_admin_panel_has_back_to_main_menu(registry: PremiumEmojiRegistry) -> None:
    keyboard = admin_keyboard(registry, owner=True)
    back = keyboard.inline_keyboard[-1][0]
    assert back.text == "Назад"
    assert back.callback_data == "admin:close"


def test_bot_commands_are_localized_without_slash_labels() -> None:
    assert [command.description for command in COMMANDS_RU] == [
        "Начать",
        "Помощь",
        "Цвета",
        "Отмена",
    ]
    assert [command.description for command in ADMIN_COMMANDS_RU][-2:] == [
        "Язык",
        "Админ-панель",
    ]
    assert [command.description for command in ADMIN_COMMANDS_EN] == [
        "Start",
        "Help",
        "Colors",
        "Cancel",
        "Language",
        "Admin panel",
    ]


@pytest.mark.asyncio
async def test_bot_commands_are_russian_for_users_and_bilingual_for_admins() -> None:
    bot = SimpleNamespace(set_my_commands=AsyncMock())
    database = SimpleNamespace(list_admins=AsyncMock(return_value=[(42, "owner")]))
    context = SimpleNamespace(database=database)

    await configure_bot_commands(bot, context)  # type: ignore[arg-type]

    calls = bot.set_my_commands.await_args_list
    assert len(calls) == 6
    assert calls[0].args == (COMMANDS_RU,)
    assert calls[1].kwargs == {"language_code": "ru"}
    assert calls[2].kwargs == {"language_code": "en"}
    assert [call.kwargs.get("language_code") for call in calls[3:]] == [
        None,
        "ru",
        "en",
    ]
    assert all(call.kwargs["scope"].chat_id == 42 for call in calls[3:])


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
