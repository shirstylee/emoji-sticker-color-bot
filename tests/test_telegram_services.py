from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.handlers.admin import admin_command
from app.models.source import MediaFormat
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
            assert len(kwargs["stickers"]) == 50  # type: ignore[arg-type]
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
    files = [
        (tmp_path / f"{index}.webp", MediaFormat.WEBP, ("🎨",)) for index in range(51)
    ]
    name = await publisher.publish_set(
        user_id=1,
        title="Pack",
        bot_username="ColorBot",
        files=files,
        custom_emoji=False,
        needs_repainting=False,
        cancel_event=asyncio.Event(),
    )
    assert name.endswith("_by_ColorBot")
    assert bot.created == 1
    assert bot.add_attempts == 2
    assert bot.successful_adds == 1


@pytest.mark.asyncio
async def test_admin_command_is_silent_for_regular_user() -> None:
    message = SimpleNamespace(from_user=SimpleNamespace(id=999), answer=AsyncMock())
    admins = SimpleNamespace(is_admin=AsyncMock(return_value=False))
    context = SimpleNamespace(admins=admins)
    await admin_command(message, context)  # type: ignore[arg-type]
    message.answer.assert_not_awaited()

