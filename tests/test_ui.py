from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.methods import EditMessageText

from app.handlers.admin import _admin_action_keyboard
from app.i18n.en import EN
from app.i18n.ru import RU
from app.keyboards.admin import admin_keyboard
from app.keyboards.user import (
    color_keyboard,
    existing_pack_keyboard,
    information_keyboard,
    intensity_keyboard,
    language_keyboard,
    main_menu_keyboard,
    pack_name_keyboard,
    processing_keyboard,
    result_keyboard,
    single_result_keyboard,
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
        for key in ("colors", "source_found", "pack_source_found"):
            assert "<blockquote><code>#FFFFFF</code>" in catalog[key]
            assert "<code>#E91E63</code>" in catalog[key]
            assert "</blockquote>" in catalog[key]


def test_rich_messages_render_with_real_premium_emoji(
    registry: PremiumEmojiRegistry,
) -> None:
    values: dict[str, object] = {
        "icon": registry.html("BRUSH"),
        "title": "Example",
        "kind": "TGS",
        "count": 1,
        "done": 1,
        "prepared": 1,
        "total": 1,
        "eta": "00:15",
        "formats": "TGS: 1",
        "color": "#2196F3",
        "intensity": "Обычная",
        "pack_list": "Example pack",
        **registry.placeholders(),
    }
    expected_icon_counts = {
        "main_menu": 5,
        "send_source": 5,
        "my_packs": 2,
        "information": 4,
        "source_found": 6,
        "pack_source_found": 6,
        "choose_output": 2,
        "pack_choose_output": 4,
        "preview_ready": 2,
        "processing": 1,
        "publishing": 4,
        "publishing_existing": 4,
        "done_file": 2,
        "done_pack": 5,
        "done_existing_pack": 3,
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
    assert "Premium Emoji — один или несколько в сообщении" in RU["send_source"]
    assert "Стикер — отдельным сообщением" in RU["send_source"]
    assert "<blockquote>Обработано:" in RU["processing"]


def test_single_result_and_information_actions(
    registry: PremiumEmojiRegistry,
) -> None:
    result = single_result_keyboard(registry, "job", "ru")
    callbacks = [
        button.callback_data
        for row in result.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert callbacks == [
        "job:job:single_pack",
        "job:job:existing",
        "job:job:intensity:soft",
        "job:job:intensity:normal",
        "job:job:intensity:vivid",
        "job:job:restart",
        "job:job:home",
    ]
    assert all("download" not in callback for callback in callbacks)
    assert result.inline_keyboard[0][0].style == "primary"
    assert result.inline_keyboard[2][1].style == "primary"
    assert result.inline_keyboard[-1][0].text == "Главное меню"

    completed = result_keyboard(registry, add_url="https://t.me/addemoji/example", language="ru")
    assert completed.inline_keyboard[-1][0].text == "Главное меню"
    assert completed.inline_keyboard[-1][0].callback_data == "menu:home"

    information = information_keyboard(registry, "ru")
    assert str(information.inline_keyboard[0][0].url) == "https://t.me/ragedick"
    assert information.inline_keyboard[0][0].style == "primary"
    assert information.inline_keyboard[1][0].callback_data == "menu:home"


def test_intensity_choice_and_failed_retry_keyboards(
    registry: PremiumEmojiRegistry,
) -> None:
    intensity = intensity_keyboard(registry, "job", "ru")
    assert [row[0].callback_data for row in intensity.inline_keyboard] == [
        "job:job:choose_intensity:soft",
        "job:job:choose_intensity:normal",
        "job:job:choose_intensity:vivid",
        "job:job:intensity_back",
    ]
    assert [row[0].text for row in intensity.inline_keyboard] == [
        "Бережная",
        "Обычная",
        "Насыщенная",
        "Назад",
    ]

    retry = result_keyboard(
        registry,
        language="ru",
        job_id="job",
        retry_errors=True,
    )
    assert retry.inline_keyboard[0][0].callback_data == "job:job:retry_failed"
    assert retry.inline_keyboard[0][0].style == "primary"
    assert retry.inline_keyboard[-2][0].callback_data == "job:job:restart"
    assert retry.inline_keyboard[-1][0].callback_data == "job:job:home"


def test_admin_existing_pack_keyboard_lists_saved_packs(
    registry: PremiumEmojiRegistry,
) -> None:
    keyboard = existing_pack_keyboard(
        registry,
        "job",
        [
            {"title": "First", "url": "https://t.me/addemoji/first_by_ColorBot"},
            {"title": "Second", "url": "https://t.me/addstickers/second_by_ColorBot"},
        ],
        "ru",
    )
    assert [row[0].callback_data for row in keyboard.inline_keyboard] == [
        "job:job:existing_saved:0",
        "job:job:existing_saved:1",
        "job:job:existing_link",
        "job:job:pack_back",
        "job:job:cancel",
    ]

    name_keyboard = pack_name_keyboard(
        registry,
        "job",
        source_title=True,
        language="ru",
    )
    assert [row[0].callback_data for row in name_keyboard.inline_keyboard] == [
        "job:job:source_title",
        "job:job:pack_back",
        "job:job:cancel",
    ]


def test_admin_panel_has_back_to_main_menu(registry: PremiumEmojiRegistry) -> None:
    keyboard = admin_keyboard(registry, owner=True)
    back = keyboard.inline_keyboard[-1][0]
    assert back.text == "Назад"
    assert back.callback_data == "admin:close"


def test_admin_subview_has_only_one_back_button(
    registry: PremiumEmojiRegistry,
) -> None:
    context = SimpleNamespace(premium=registry)
    keyboard = _admin_action_keyboard(context, "refresh", "Назад")  # type: ignore[arg-type]
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert len(buttons) == 1
    assert buttons[0].callback_data == "admin:refresh"


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


@pytest.mark.asyncio
async def test_edit_retry_after_does_not_abort_background_work(
    registry: PremiumEmojiRegistry,
) -> None:
    retry = TelegramRetryAfter(
        method=EditMessageText(chat_id=1, message_id=1, text="progress"),
        message="Too Many Requests",
        retry_after=506,
    )
    fresh = SimpleNamespace(message_id=2)
    message = SimpleNamespace(
        edit_text=AsyncMock(side_effect=retry),
        answer=AsyncMock(return_value=fresh),
    )
    ui = SafeUI(registry)

    skipped = await ui.edit(message, "progress", retry_as_answer=False)  # type: ignore[arg-type]
    delivered = await ui.edit(message, "done")  # type: ignore[arg-type]

    assert skipped is message
    assert delivered is fresh
    message.answer.assert_awaited_once()
