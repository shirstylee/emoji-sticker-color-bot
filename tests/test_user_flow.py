from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.enums import StickerType
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import GetStickerSet
from aiogram.types import Chat, Message, MessageEntity, User

from app.handlers.commands import cancel_callback, cancel_command, menu_callback, start
from app.handlers.workflow import (
    _looks_like_new_source,
    _select_existing_pack,
    job_callback,
    private_message,
)
from app.models.job import JobStatus
from app.models.source import MediaFormat, SourceDescriptor, SourceItem, SourceKind
from app.services.jobs import JobManager
from app.services.premium_emoji import PremiumEmojiRegistry


@pytest.mark.asyncio
async def test_regular_start_is_russian_without_language_or_packs() -> None:
    registry = PremiumEmojiRegistry.load(Path("Main.txt"))
    sent = SimpleNamespace(message_id=20)
    context = SimpleNamespace(
        premium=registry,
        ui=SimpleNamespace(answer=AsyncMock(return_value=sent)),
        bot=SimpleNamespace(delete_message=AsyncMock()),
        menu_messages={},
        languages={},
        admins=SimpleNamespace(is_admin=AsyncMock(return_value=False)),
    )
    message = SimpleNamespace(
        chat=SimpleNamespace(id=7, type="private"),
        from_user=SimpleNamespace(id=7),
        delete=AsyncMock(),
    )

    await start(message, context)  # type: ignore[arg-type]

    call = context.ui.answer.await_args
    markup = call.kwargs["reply_markup"]
    assert "Выберите действие" in call.args[1]
    assert [row[0].text for row in markup.inline_keyboard] == [
        "Покрасить эмодзи",
        "Информация",
    ]
    assert context.menu_messages[7] == (7, 20)
    message.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_start_uses_saved_language_without_prompt() -> None:
    registry = PremiumEmojiRegistry.load(Path("Main.txt"))
    sent = SimpleNamespace(message_id=20)
    context = SimpleNamespace(
        premium=registry,
        ui=SimpleNamespace(answer=AsyncMock(return_value=sent)),
        bot=SimpleNamespace(delete_message=AsyncMock()),
        menu_messages={},
        languages={7: "en"},
        admins=SimpleNamespace(is_admin=AsyncMock(return_value=True)),
    )
    message = SimpleNamespace(
        chat=SimpleNamespace(id=7, type="private"),
        from_user=SimpleNamespace(id=7),
        delete=AsyncMock(),
    )

    await start(message, context)  # type: ignore[arg-type]

    markup = context.ui.answer.await_args.kwargs["reply_markup"]
    assert "Choose an action" in context.ui.answer.await_args.args[1]
    assert [row[0].text for row in markup.inline_keyboard] == [
        "Recolor Emoji",
        "My packs",
        "Information",
    ]


@pytest.mark.asyncio
async def test_my_packs_removes_deleted_sets_but_keeps_unverified_sets() -> None:
    registry = PremiumEmojiRegistry.load(Path("Main.txt"))
    packs = [
        {
            "title": "Active",
            "url": "https://t.me/addemoji/active_by_bot",
            "kind": "emoji",
        },
        {
            "title": "Temporarily unavailable",
            "url": "https://t.me/addstickers/unavailable_by_bot",
            "kind": "sticker",
        },
        {
            "title": "Deleted",
            "url": "https://t.me/addemoji/deleted_by_bot",
            "kind": "emoji",
        },
    ]

    async def get_sticker_set(name: str) -> object:
        if name == "deleted_by_bot":
            raise TelegramBadRequest(
                method=GetStickerSet(name=name),
                message="Bad Request: STICKERSET_INVALID",
            )
        if name == "unavailable_by_bot":
            raise ConnectionError("temporary network failure")
        return object()

    control = Message(
        message_id=50,
        date=0,
        chat=Chat(id=7, type="private"),
        from_user=User(id=999, is_bot=True, first_name="Bot"),
        text="Menu",
    )
    callback = SimpleNamespace(
        data="menu:packs",
        message=control,
        from_user=SimpleNamespace(id=7),
        answer=AsyncMock(),
    )
    admins = SimpleNamespace(
        is_admin=AsyncMock(return_value=True),
        packs=AsyncMock(return_value=packs),
        forget_packs=AsyncMock(),
    )
    context = SimpleNamespace(
        premium=registry,
        ui=SimpleNamespace(edit=AsyncMock()),
        bot=SimpleNamespace(get_sticker_set=AsyncMock(side_effect=get_sticker_set)),
        menu_messages={},
        languages={7: "ru"},
        admins=admins,
    )

    await menu_callback(callback, context)  # type: ignore[arg-type]

    admins.forget_packs.assert_awaited_once_with(
        7, ["https://t.me/addemoji/deleted_by_bot"]
    )
    rendered = context.ui.edit.await_args.args[1]
    assert "Active" in rendered
    assert "Temporarily unavailable" in rendered
    assert "Deleted" not in rendered


@pytest.mark.asyncio
async def test_admin_can_submit_another_source_while_job_is_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    accept = AsyncMock()
    monkeypatch.setattr("app.handlers.workflow._accept_source", accept)
    active_job = SimpleNamespace(
        status=JobStatus.PROCESSING,
        created_at=0,
        language="ru",
        job_id="current",
    )
    context = SimpleNamespace(
        admins=SimpleNamespace(is_admin=AsyncMock(return_value=True)),
        jobs=SimpleNamespace(for_user=lambda _user_id: [active_job]),
    )
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=7),
        document=SimpleNamespace(),
        sticker=None,
        text=None,
        media_group_id=None,
    )

    await private_message(message, context)  # type: ignore[arg-type]

    accept.assert_awaited_once_with(message, context)


def test_hex_hashtag_entity_is_a_color_not_a_new_source() -> None:
    message = Message(
        message_id=1,
        date=0,
        chat=Chat(id=7, type="private"),
        from_user=User(id=7, is_bot=False, first_name="User"),
        text="#FF9800",
        entities=[MessageEntity(type="hashtag", offset=0, length=7)],
    )

    assert not _looks_like_new_source(message)


@pytest.mark.asyncio
async def test_processing_job_can_be_cancelled_from_inline_button(tmp_path: Path) -> None:
    registry = PremiumEmojiRegistry.load(Path("Main.txt"))
    jobs = JobManager(tmp_path / "jobs")
    await jobs.startup_cleanup()
    job = await jobs.create(user_id=7, chat_id=7, language="ru", is_admin=False)
    job.status = JobStatus.PROCESSING
    control = Message(
        message_id=50,
        date=0,
        chat=Chat(id=7, type="private"),
        from_user=User(id=999, is_bot=True, first_name="Bot"),
        text="Processing",
    )
    callback = SimpleNamespace(
        data=f"job:{job.job_id}:cancel",
        message=control,
        from_user=SimpleNamespace(id=7),
        answer=AsyncMock(),
    )
    context = SimpleNamespace(
        admins=SimpleNamespace(is_admin=AsyncMock(return_value=False)),
        jobs=jobs,
        ui=SimpleNamespace(edit=AsyncMock(return_value=control)),
        premium=registry,
        publisher=SimpleNamespace(delete_sets=AsyncMock()),
    )

    await job_callback(callback, context)  # type: ignore[arg-type]

    callback.answer.assert_awaited_once()
    context.ui.edit.assert_awaited_once()
    assert "Задача отменена" in context.ui.edit.await_args.args[1]
    assert job.cancel_event.is_set()
    assert jobs.get(job.job_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("is_admin", [False, True])
async def test_existing_pack_selection_uses_links_for_users_and_saved_packs_for_admins(
    tmp_path: Path,
    is_admin: bool,
) -> None:
    registry = PremiumEmojiRegistry.load(Path("Main.txt"))
    jobs = JobManager(tmp_path / ("admin-jobs" if is_admin else "user-jobs"))
    await jobs.startup_cleanup()
    job = await jobs.create(
        user_id=7,
        chat_id=7,
        language="ru",
        is_admin=is_admin,
    )
    control = Message(
        message_id=50,
        date=0,
        chat=Chat(id=7, type="private"),
        from_user=User(id=999, is_bot=True, first_name="Bot"),
        text="Done",
    )
    callback = SimpleNamespace(
        data=f"job:{job.job_id}:existing",
        message=control,
        from_user=SimpleNamespace(id=7),
        answer=AsyncMock(),
    )
    packs = [
        {
            "title": "Saved pack",
            "url": "https://t.me/addemoji/saved_by_ColorBot",
        }
    ]
    admins = SimpleNamespace(
        is_admin=AsyncMock(return_value=is_admin),
        packs=AsyncMock(return_value=packs),
    )
    context = SimpleNamespace(
        admins=admins,
        jobs=jobs,
        ui=SimpleNamespace(edit=AsyncMock(return_value=control)),
        premium=registry,
    )

    await job_callback(callback, context)  # type: ignore[arg-type]

    assert job.status == JobStatus.AWAITING_TARGET_PACK
    rendered = context.ui.edit.await_args.args[1]
    markup = context.ui.edit.await_args.kwargs["reply_markup"]
    if is_admin:
        assert "Выберите один из своих наборов" in rendered
        assert markup.inline_keyboard[0][0].text == "Saved pack"
        admins.packs.assert_awaited_once_with(7)
    else:
        assert "Отправьте ссылку" in rendered
        admins.packs.assert_not_awaited()

    job.source = SourceDescriptor(
        kind=SourceKind.CUSTOM_EMOJI,
        items=[SourceItem(1, tmp_path / "one.webp", MediaFormat.WEBP)],
    )
    job.selected_color = "#8B00FF"
    callback.data = f"job:{job.job_id}:pack_back"
    await job_callback(callback, context)  # type: ignore[arg-type]

    assert job.status == JobStatus.AWAITING_RESULT_ACTION
    back_markup = context.ui.edit.await_args.kwargs["reply_markup"]
    assert back_markup.inline_keyboard[0][0].callback_data == (
        f"job:{job.job_id}:single_pack"
    )


@pytest.mark.asyncio
async def test_existing_pack_accepts_aiogram_sticker_type_enum(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = PremiumEmojiRegistry.load(Path("Main.txt"))
    jobs = JobManager(tmp_path / "jobs")
    await jobs.startup_cleanup()
    job = await jobs.create(user_id=7, chat_id=7, language="ru", is_admin=False)
    job.source = SourceDescriptor(
        kind=SourceKind.CUSTOM_EMOJI,
        items=[SourceItem(1, tmp_path / "one.webp", MediaFormat.WEBP)],
    )
    sticker_set = SimpleNamespace(
        sticker_type=StickerType.CUSTOM_EMOJI,
        stickers=[SimpleNamespace(needs_repainting=False)],
        title="Existing",
    )
    start_processing = AsyncMock()
    monkeypatch.setattr("app.handlers.workflow._start_processing", start_processing)
    control = Message(
        message_id=50,
        date=0,
        chat=Chat(id=7, type="private"),
        from_user=User(id=999, is_bot=True, first_name="Bot"),
        text="Choose",
    )
    context = SimpleNamespace(
        bot_username="ColorBot",
        bot=SimpleNamespace(get_sticker_set=AsyncMock(return_value=sticker_set)),
        ui=SimpleNamespace(edit=AsyncMock(return_value=control), answer=AsyncMock()),
        premium=registry,
    )

    accepted = await _select_existing_pack(
        control,
        job,
        context,  # type: ignore[arg-type]
        "https://t.me/addemoji/existing_by_ColorBot",
    )

    assert accepted
    assert job.target_pack_name == "existing_by_ColorBot"
    start_processing.assert_awaited_once_with(control, job, context)

    job.adaptive = True
    sticker_set.sticker_type = StickerType.REGULAR
    rejected = await _select_existing_pack(
        control,
        job,
        context,  # type: ignore[arg-type]
        "https://t.me/addstickers/existing_by_ColorBot",
    )

    assert not rejected
    assert "Adaptive Emoji" in context.ui.answer.await_args.args[1]
    start_processing.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_menu_lists_jobs_and_can_cancel_last_then_all(tmp_path: Path) -> None:
    registry = PremiumEmojiRegistry.load(Path("Main.txt"))
    jobs = JobManager(tmp_path / "cancel-jobs")
    await jobs.startup_cleanup()
    first = await jobs.create(user_id=7, chat_id=7, language="ru", is_admin=True)
    first.status = JobStatus.PROCESSING
    first.progress = 8
    first.total = 16
    second = await jobs.create(user_id=7, chat_id=7, language="ru", is_admin=True)
    second.status = JobStatus.AWAITING_COLOR
    second.total = 1
    sent = SimpleNamespace(message_id=60)
    ui = SimpleNamespace(
        answer=AsyncMock(return_value=sent),
        edit=AsyncMock(),
    )
    context = SimpleNamespace(
        admins=SimpleNamespace(is_admin=AsyncMock(return_value=True)),
        languages={7: "ru"},
        jobs=jobs,
        premium=registry,
        ui=ui,
        bot=SimpleNamespace(edit_message_reply_markup=AsyncMock()),
        publisher=SimpleNamespace(delete_sets=AsyncMock()),
    )
    command = SimpleNamespace(
        from_user=SimpleNamespace(id=7),
        chat=SimpleNamespace(id=7, type="private"),
    )

    await cancel_command(command, context)  # type: ignore[arg-type]

    body = ui.answer.await_args.args[1]
    markup = ui.answer.await_args.kwargs["reply_markup"]
    assert "Активных задач: <b>2</b>" in body
    assert f"#{first.short_id}" in body and f"#{second.short_id}" in body
    assert "<blockquote>" in body
    assert [row[0].callback_data for row in markup.inline_keyboard] == [
        "cancel:last",
        "cancel:all",
    ]

    menu = Message(
        message_id=60,
        date=0,
        chat=Chat(id=7, type="private"),
        from_user=User(id=999, is_bot=True, first_name="Bot"),
        text="Cancel",
    )
    callback = SimpleNamespace(
        data="cancel:last",
        message=menu,
        from_user=SimpleNamespace(id=7),
        answer=AsyncMock(),
    )
    await cancel_callback(callback, context)  # type: ignore[arg-type]

    assert jobs.get(second.job_id) is None
    assert jobs.get(first.job_id) is first
    assert "Последняя задача отменена" in ui.edit.await_args.args[1]

    callback.data = "cancel:all"
    await cancel_callback(callback, context)  # type: ignore[arg-type]

    assert jobs.active_count == 0
    assert "Все активные задачи отменены" in ui.edit.await_args.args[1]
