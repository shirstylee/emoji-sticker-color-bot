from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendSticker
from aiogram.types import FSInputFile

from app.database.admins import AdminService
from app.handlers.admin import admin_command
from app.models.source import MediaFormat
from app.services.premium_emoji import PremiumEmojiRegistry
from app.services.telegram_rate_limiter import TelegramStickerRateController
from app.services.telegram_stickers import StickerPublisher, generate_short_name, pack_url


class RetryError(Exception):
    def __init__(self, retry_after: float) -> None:
        self.retry_after = retry_after


@pytest.mark.parametrize(
    "title",
    ["My Beautiful Pack", "123 цифры", "___", "A" * 200, "emoji & sticker"],
)
def test_short_name_valid_length_and_suffix(title: str) -> None:
    result = generate_short_name(title, "ColorBot", token_factory=lambda: "abc123")
    assert result.endswith("_by_ColorBot")
    assert result[0].isalpha()
    assert len(result) <= 64
    assert "__" not in result
    assert all(char.isascii() and (char.isalnum() or char == "_") for char in result)


def test_pack_urls_do_not_mix_routes() -> None:
    assert pack_url("name", custom_emoji=True) == "https://t.me/addemoji/name"
    assert pack_url("name", custom_emoji=False) == "https://t.me/addstickers/name"


@pytest.mark.asyncio
async def test_retry_after_resumes_same_operation() -> None:
    controller = TelegramStickerRateController()
    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RetryError(0.01)
        return "ok"

    assert await controller.call(operation, asyncio.Event()) == "ok"
    assert attempts == 2
    assert controller.last_retry_after == 0.01


@pytest.mark.asyncio
async def test_flood_callback_receives_live_countdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]

    async def fake_sleep(seconds: float, _cancel: asyncio.Event) -> None:
        clock[0] += seconds

    monkeypatch.setattr(
        "app.services.telegram_rate_limiter.time.monotonic", lambda: clock[0]
    )
    monkeypatch.setattr(
        "app.services.telegram_rate_limiter.cancellation_aware_sleep", fake_sleep
    )
    controller = TelegramStickerRateController()
    attempts = 0
    countdown: list[float] = []

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RetryError(2.2)
        return "ok"

    async def on_flood(remaining: float) -> None:
        countdown.append(remaining)

    assert await controller.call(
        operation, asyncio.Event(), on_flood=on_flood
    ) == "ok"
    assert countdown == [3.0, 2.0, 1.0]


@pytest.mark.asyncio
async def test_cancellation_during_flood_wait() -> None:
    controller = TelegramStickerRateController()
    cancel = asyncio.Event()
    called = asyncio.Event()

    async def operation() -> None:
        called.set()
        raise RetryError(30)

    task = asyncio.create_task(controller.call(operation, cancel))
    await called.wait()
    cancel.set()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_429_pack_integration_does_not_duplicate_items(tmp_path: Path) -> None:
    class FakeBot:
        def __init__(self) -> None:
            self.created = 0
            self.add_attempts = 0
            self.successful_adds = 0

        async def create_new_sticker_set(self, **kwargs: object) -> bool:
            self.created += 1
            assert len(kwargs["stickers"]) == 8  # type: ignore[arg-type]
            return True

        async def add_sticker_to_set(self, **_: object) -> bool:
            self.add_attempts += 1
            if self.add_attempts == 1:
                raise RetryError(0.01)
            self.successful_adds += 1
            return True

        async def delete_sticker_set(self, _: str) -> bool:
            return True

    bot = FakeBot()
    publisher = StickerPublisher(bot, TelegramStickerRateController())  # type: ignore[arg-type]
    progress: list[tuple[int, int]] = []
    files = [
        (tmp_path / f"{index}.webp", MediaFormat.WEBP, ("🎨",)) for index in range(9)
    ]
    name = await publisher.publish_set(
        user_id=1,
        title="Pack",
        bot_username="ColorBot",
        files=files,
        custom_emoji=False,
        needs_repainting=False,
        cancel_event=asyncio.Event(),
        on_progress=lambda done, total: _append_progress(progress, done, total),
    )
    assert name.endswith("_by_ColorBot")
    assert bot.created == 1
    assert bot.add_attempts == 2
    assert bot.successful_adds == 1
    assert progress == [(8, 9), (9, 9)]


@pytest.mark.asyncio
async def test_pack_creation_batches_initial_eight_and_reports_live_progress(
    tmp_path: Path,
) -> None:
    class FakeBot:
        def __init__(self) -> None:
            self.initial = 0
            self.added = 0

        async def create_new_sticker_set(self, **kwargs: object) -> bool:
            self.initial = len(kwargs["stickers"])  # type: ignore[arg-type]
            return True

        async def add_sticker_to_set(self, **_: object) -> bool:
            self.added += 1
            return True

        async def set_custom_emoji_sticker_set_thumbnail(self, **_: object) -> bool:
            return True

        async def get_sticker_set(self, _: str) -> object:
            return SimpleNamespace(stickers=[])

    bot = FakeBot()
    publisher = StickerPublisher(bot, TelegramStickerRateController())  # type: ignore[arg-type]
    progress: list[tuple[int, int]] = []
    files = [
        (tmp_path / f"{index}.tgs", MediaFormat.TGS, ("🎨",))
        for index in range(19)
    ]

    await publisher.publish_set(
        user_id=1,
        title="Pack",
        bot_username="ColorBot",
        files=files,
        custom_emoji=True,
        needs_repainting=False,
        cancel_event=asyncio.Event(),
        on_progress=lambda done, total: _append_progress(progress, done, total),
    )

    assert bot.initial == 8
    assert bot.added == 11
    assert progress == [(done, 19) for done in range(8, 20)]


@pytest.mark.asyncio
async def test_append_to_existing_set_reports_each_success(tmp_path: Path) -> None:
    class FakeBot:
        def __init__(self) -> None:
            self.names: list[str] = []

        async def add_sticker_to_set(self, **kwargs: object) -> bool:
            self.names.append(str(kwargs["name"]))
            return True

    bot = FakeBot()
    controller = TelegramStickerRateController(conservative_enabled=False)
    publisher = StickerPublisher(bot, controller)  # type: ignore[arg-type]
    progress: list[tuple[int, int]] = []
    files = [
        (tmp_path / f"{index}.webp", MediaFormat.WEBP, ("🎨",))
        for index in range(2)
    ]

    await publisher.append_to_set(
        user_id=1,
        name="saved_by_ColorBot",
        files=files,
        cancel_event=asyncio.Event(),
        on_progress=lambda done, total: _append_progress(progress, done, total),
    )

    assert bot.names == ["saved_by_ColorBot", "saved_by_ColorBot"]
    assert progress == [(1, 2), (2, 2)]


@pytest.mark.asyncio
async def test_conservative_pack_window_counts_items_and_skips_chat_sends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]

    async def fake_sleep(seconds: float, _cancel: asyncio.Event) -> None:
        clock[0] += seconds

    monkeypatch.setattr(
        "app.services.telegram_rate_limiter.time.monotonic", lambda: clock[0]
    )
    monkeypatch.setattr(
        "app.services.telegram_rate_limiter.cancellation_aware_sleep", fake_sleep
    )
    controller = TelegramStickerRateController(
        conservative_enabled=True,
        conservative_requests=8,
        conservative_window_seconds=240,
    )
    cancel = asyncio.Event()
    countdown: list[float] = []

    async def operation() -> str:
        return "ok"

    await controller.call(
        operation,
        cancel,
        conservative=True,
        conservative_cost=8,
    )
    assert await controller.call(operation, cancel, conservative=False) == "ok"
    assert clock[0] == 0.0

    await controller.call(
        operation,
        cancel,
        conservative=True,
        on_flood=lambda remaining: _append_countdown(countdown, remaining),
    )

    assert clock[0] == 240.0
    assert countdown[0] == 240.0
    assert countdown[-1] == 1.0


@pytest.mark.asyncio
async def test_conservative_pack_eta_accounts_for_multiple_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.telegram_rate_limiter.time.monotonic", lambda: 100.0
    )
    controller = TelegramStickerRateController(
        conservative_enabled=True,
        conservative_requests=8,
        conservative_window_seconds=240,
    )

    assert await controller.estimate_conservative_delay(8) == 0.0
    assert await controller.estimate_conservative_delay(9) == 240.0
    assert await controller.estimate_conservative_delay(19) == 480.0


@pytest.mark.asyncio
async def test_retry_after_does_not_reserve_local_window_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]

    async def fake_sleep(seconds: float, _cancel: asyncio.Event) -> None:
        clock[0] += seconds

    monkeypatch.setattr(
        "app.services.telegram_rate_limiter.time.monotonic", lambda: clock[0]
    )
    monkeypatch.setattr(
        "app.services.telegram_rate_limiter.cancellation_aware_sleep", fake_sleep
    )
    controller = TelegramStickerRateController(
        conservative_enabled=True,
        conservative_requests=1,
        conservative_window_seconds=10,
    )
    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RetryError(2)
        return "ok"

    assert await controller.call(
        operation,
        asyncio.Event(),
        conservative=True,
    ) == "ok"

    assert attempts == 2
    assert clock[0] == 2.0


async def _append_progress(
    target: list[tuple[int, int]], done: int, total: int
) -> None:
    target.append((done, total))


async def _append_countdown(target: list[float], remaining: float) -> None:
    target.append(remaining)


@pytest.mark.asyncio
async def test_wrong_file_type_uploads_before_retrying_pack_creation(
    tmp_path: Path,
) -> None:
    class FakeBot:
        def __init__(self) -> None:
            self.create_calls: list[dict[str, object]] = []
            self.uploads = 0

        async def create_new_sticker_set(self, **kwargs: object) -> bool:
            self.create_calls.append(kwargs)
            if len(self.create_calls) == 1:
                raise TelegramBadRequest(
                    SendSticker(chat_id=1, sticker="invalid"),
                    "Bad Request: wrong file type",
                )
            return True

        async def upload_sticker_file(self, **_: object) -> object:
            self.uploads += 1
            return SimpleNamespace(file_id="uploaded-file-id")

    path = tmp_path / "one.webp"
    path.write_bytes(b"payload")
    bot = FakeBot()
    publisher = StickerPublisher(bot, TelegramStickerRateController())  # type: ignore[arg-type]

    await publisher.publish_set(
        user_id=1,
        title="Pack",
        bot_username="ColorBot",
        files=[(path, MediaFormat.WEBP, ("🎨",))],
        custom_emoji=True,
        needs_repainting=False,
        cancel_event=asyncio.Event(),
    )

    assert bot.uploads == 1
    retried = bot.create_calls[1]["stickers"]
    assert retried[0].sticker == "uploaded-file-id"  # type: ignore[index]


@pytest.mark.asyncio
async def test_tgs_pack_retries_with_uploaded_file_id_only_after_native_failure(
    tmp_path: Path,
) -> None:
    class FakeBot:
        def __init__(self) -> None:
            self.create_calls: list[dict[str, object]] = []
            self.uploads = 0

        async def create_new_sticker_set(self, **kwargs: object) -> bool:
            self.create_calls.append(kwargs)
            if len(self.create_calls) == 1:
                raise TelegramBadRequest(
                    SendSticker(chat_id=1, sticker="invalid"),
                    "Bad Request: wrong file type",
                )
            return True

        async def upload_sticker_file(self, **_: object) -> object:
            self.uploads += 1
            return SimpleNamespace(file_id="uploaded-tgs-id")

    path = tmp_path / "one.tgs"
    path.write_bytes(b"payload")
    bot = FakeBot()
    publisher = StickerPublisher(bot, TelegramStickerRateController())  # type: ignore[arg-type]

    await publisher.publish_set(
        user_id=1,
        title="Animated Pack",
        bot_username="ColorBot",
        files=[(path, MediaFormat.TGS, ("🎨",))],
        custom_emoji=True,
        needs_repainting=False,
        cancel_event=asyncio.Event(),
    )

    first = bot.create_calls[0]["stickers"]
    second = bot.create_calls[1]["stickers"]
    assert isinstance(first[0].sticker, FSInputFile)  # type: ignore[index]
    assert second[0].sticker == "uploaded-tgs-id"  # type: ignore[index]
    assert bot.uploads == 1


@pytest.mark.asyncio
async def test_sticker_send_uses_multipart_asset_without_pack_upload(tmp_path: Path) -> None:
    class FakeBot:
        def __init__(self) -> None:
            self.sent: list[object] = []

        async def send_sticker(self, **kwargs: object) -> object:
            self.sent.append(kwargs["sticker"])
            return SimpleNamespace(message_id=7)

        async def upload_sticker_file(self, **_: object) -> object:
            raise AssertionError("chat delivery must not use uploadStickerFile")

    path = tmp_path / "one.webm"
    path.write_bytes(b"payload")
    bot = FakeBot()
    publisher = StickerPublisher(bot, TelegramStickerRateController())  # type: ignore[arg-type]

    result = await publisher.send_sticker_file(
        chat_id=1,
        path=path,
        media_format=MediaFormat.WEBM,
        cancel_event=asyncio.Event(),
    )

    assert result.message_id == 7  # type: ignore[attr-defined]
    assert len(bot.sent) == 1
    assert isinstance(bot.sent[0], FSInputFile)


@pytest.mark.asyncio
async def test_tgs_is_sent_as_a_native_multipart_sticker(tmp_path: Path) -> None:
    class FakeBot:
        def __init__(self) -> None:
            self.events: list[tuple[str, object]] = []

        async def upload_sticker_file(self, **_: object) -> object:
            self.events.append(("upload", "tgs"))
            return SimpleNamespace(file_id="uploaded-tgs-id")

        async def send_sticker(self, **kwargs: object) -> object:
            self.events.append(("send", kwargs["sticker"]))
            return SimpleNamespace(message_id=8)

    path = tmp_path / "one.tgs"
    path.write_bytes(b"payload")
    bot = FakeBot()
    publisher = StickerPublisher(bot, TelegramStickerRateController())  # type: ignore[arg-type]

    await publisher.send_sticker_file(
        chat_id=1,
        path=path,
        media_format=MediaFormat.TGS,
        cancel_event=asyncio.Event(),
    )

    assert len(bot.events) == 1
    assert bot.events[0][0] == "send"
    assert isinstance(bot.events[0][1], FSInputFile)


@pytest.mark.asyncio
async def test_tgs_pack_creation_uses_native_multipart_upload(tmp_path: Path) -> None:
    class FakeBot:
        def __init__(self) -> None:
            self.created_sticker: object | None = None

        async def upload_sticker_file(self, **_: object) -> object:
            raise AssertionError("native TGS should be attempted before pre-upload fallback")

        async def create_new_sticker_set(self, **kwargs: object) -> bool:
            self.created_sticker = kwargs["stickers"][0].sticker  # type: ignore[index]
            return True

    path = tmp_path / "one.tgs"
    path.write_bytes(b"payload")
    bot = FakeBot()
    publisher = StickerPublisher(bot, TelegramStickerRateController())  # type: ignore[arg-type]

    await publisher.publish_set(
        user_id=1,
        title="Adaptive Pack",
        bot_username="ColorBot",
        files=[(path, MediaFormat.TGS, ("🎨",))],
        custom_emoji=True,
        needs_repainting=True,
        cancel_event=asyncio.Event(),
    )

    assert isinstance(bot.created_sticker, FSInputFile)


@pytest.mark.asyncio
async def test_admin_command_is_silent_for_regular_user() -> None:
    message = SimpleNamespace(from_user=SimpleNamespace(id=999), answer=AsyncMock())
    admins = SimpleNamespace(owner_id=777, is_admin=AsyncMock(return_value=False))
    context = SimpleNamespace(admins=admins)
    await admin_command(message, context)  # type: ignore[arg-type]
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_configured_owner_is_authoritative_without_database_row() -> None:
    database = SimpleNamespace(is_admin=AsyncMock(return_value=False))
    admins = AdminService(database, owner_id=777)  # type: ignore[arg-type]

    assert await admins.is_admin(777)
    assert await admins.is_owner(777)
    database.is_admin.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_command_answers_configured_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = SimpleNamespace(is_admin=AsyncMock(return_value=False))
    context = SimpleNamespace(
        admins=AdminService(database, owner_id=777),  # type: ignore[arg-type]
        premium=PremiumEmojiRegistry.load(Path("Main.txt")),
        ui=SimpleNamespace(answer=AsyncMock()),
    )
    message = SimpleNamespace(from_user=SimpleNamespace(id=777))
    dashboard = AsyncMock(return_value="admin dashboard")
    monkeypatch.setattr("app.handlers.admin._safe_dashboard", dashboard)

    await admin_command(message, context)  # type: ignore[arg-type]

    context.ui.answer.assert_awaited_once()
    assert context.ui.answer.await_args.args[1] == "admin dashboard"
