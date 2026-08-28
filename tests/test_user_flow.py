from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, Message, MessageEntity, User

from app.handlers.commands import start
from app.handlers.workflow import _looks_like_new_source, job_callback, private_message
from app.models.job import JobStatus
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
