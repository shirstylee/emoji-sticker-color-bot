"""Emoji & Sticker Color Bot entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import tempfile
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.types import BotCommand, BotCommandScopeChat

from app.config import Settings, discover_emoji_font
from app.context import AppContext
from app.database.admins import AdminService
from app.database.connection import Database
from app.database.settings import load_limits
from app.handlers import register_handlers
from app.i18n import text
from app.logging import ErrorBuffer, configure_logging
from app.models.job import RuntimeJob
from app.recolor.webm import ffmpeg_executable
from app.services.jobs import JobManager
from app.services.media_groups import MediaGroupCollector
from app.services.pipeline import ProcessingPipeline
from app.services.premium_emoji import PremiumEmojiRegistry
from app.services.scheduler import JobScheduler
from app.services.telegram_rate_limiter import TelegramStickerRateController
from app.services.telegram_stickers import StickerPublisher
from app.services.ui import SafeUI, fallback_html, premium_error
from app.services.user_rate_limiter import UserRateLimiter

LOGGER = logging.getLogger(__name__)

COMMANDS_RU = [
    BotCommand(command="start", description="Начать"),
    BotCommand(command="help", description="Помощь"),
    BotCommand(command="colors", description="Цвета"),
    BotCommand(command="cancel", description="Отмена"),
]

ADMIN_COMMANDS_RU = [
    *COMMANDS_RU,
    BotCommand(command="language", description="Язык"),
    BotCommand(command="admin", description="Админ-панель"),
]

ADMIN_COMMANDS_EN = [
    BotCommand(command="start", description="Start"),
    BotCommand(command="help", description="Help"),
    BotCommand(command="colors", description="Colors"),
    BotCommand(command="cancel", description="Cancel"),
    BotCommand(command="language", description="Language"),
    BotCommand(command="admin", description="Admin panel"),
]


def load_settings() -> Settings:
    settings = Settings()
    settings.emoji_font_path = discover_emoji_font(settings.emoji_font_path)
    return settings


def build_scheduler(settings: Settings) -> JobScheduler:
    return JobScheduler(
        temp_root=settings.temp_root,
        global_workers=settings.global_running_jobs,
        tgs_workers=settings.tgs_workers,
        raster_workers=settings.raster_workers,
        webm_workers=settings.webm_workers,
        archive_workers=settings.archive_workers,
        preview_workers=settings.preview_workers,
        pending_regular=settings.global_pending_regular,
        ram_min_mib=settings.ram_safety_min_mib,
        disk_min_mib=settings.disk_safety_min_mib,
    )


async def build_context(settings: Settings, bot: Bot, bot_username: str) -> AppContext:
    database = Database(settings.database_path)
    await database.open()
    await database.ensure_owner(settings.owner_id)
    await database.assert_privacy_schema()
    premium = PremiumEmojiRegistry.load(settings.premium_emoji_path)
    jobs = JobManager(settings.temp_root, settings.job_idle_timeout_seconds)
    await jobs.startup_cleanup()
    limits = await load_limits(database)
    scheduler = build_scheduler(settings)
    scheduler.start()

    async def record_flood(_: float) -> None:
        await database.increment_statistics({"telegram_429": 1})

    conservative_enabled = bool(
        await database.get_setting(
            "telegram_sticker_conservative_limit_enabled",
            settings.telegram_sticker_conservative_limit_enabled,
        )
    )
    telegram_limiter = TelegramStickerRateController(
        conservative_enabled=conservative_enabled,
        conservative_requests=settings.telegram_sticker_conservative_requests,
        conservative_window_seconds=settings.telegram_sticker_conservative_window_seconds,
        on_flood=record_flood,
    )
    context = AppContext(
        bot=bot,
        bot_username=bot_username,
        settings=settings,
        database=database,
        admins=AdminService(database, settings.owner_id),
        jobs=jobs,
        scheduler=scheduler,
        pipeline=ProcessingPipeline(settings, scheduler),
        user_limiter=UserRateLimiter(limits),
        telegram_limiter=telegram_limiter,
        publisher=StickerPublisher(bot, telegram_limiter),
        premium=premium,
        ui=SafeUI(premium),
        media_groups=MediaGroupCollector(),
        limits=limits,
        errors=ErrorBuffer(),
        languages={
            user_id: await database.admin_language(user_id)
            for user_id, _role in await database.list_admins()
        },
    )

    async def timeout_notification(runtime_job: RuntimeJob) -> None:
        body = f'{premium.html("TIME")} {text(runtime_job.language, "timeout")}'
        try:
            await bot.send_message(runtime_job.chat_id, body)
        except TelegramBadRequest as error:
            if not premium_error(error):
                return
            premium.disable()
            try:
                await bot.send_message(runtime_job.chat_id, fallback_html(body))
            except Exception:
                return
        except Exception:
            return

    jobs.start_sweeper(timeout_notification)
    return context


async def shutdown_context(context: AppContext) -> None:
    context.shutdown_requested = True
    context.scheduler.accepting = False
    await context.media_groups.shutdown()
    await context.jobs.shutdown()
    await context.scheduler.shutdown()
    await context.database.close()


async def configure_bot_commands(bot: Bot, context: AppContext) -> None:
    # Ordinary users always see the Russian-only command set. Explicitly replace
    # old EN command scopes left by earlier deployments.
    await bot.set_my_commands(COMMANDS_RU)
    await bot.set_my_commands(COMMANDS_RU, language_code="ru")
    await bot.set_my_commands(COMMANDS_RU, language_code="en")
    for user_id, _role in await context.database.list_admins():
        scope = BotCommandScopeChat(chat_id=user_id)
        try:
            await bot.set_my_commands(ADMIN_COMMANDS_RU, scope=scope)
            await bot.set_my_commands(
                ADMIN_COMMANDS_RU, scope=scope, language_code="ru"
            )
            await bot.set_my_commands(
                ADMIN_COMMANDS_EN, scope=scope, language_code="en"
            )
        except TelegramBadRequest:
            # An administrator may not have opened the bot yet. This must never
            # prevent polling or owner access from starting.
            LOGGER.warning("Could not install a private admin command scope")


async def run_bot() -> None:
    settings = load_settings()
    settings.validate_runtime()
    configure_logging(settings.log_dir, settings.log_level)
    ffmpeg = ffmpeg_executable()
    LOGGER.info("FFmpeg discovery succeeded | executable=%s", ffmpeg.name)
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    context: AppContext | None = None
    try:
        identity = await bot.get_me()
        if not identity.username:
            raise RuntimeError("Bot username is required for sticker set short names")
        context = await build_context(settings, bot, identity.username)
        dispatcher = Dispatcher(
            storage=MemoryStorage(),
            events_isolation=SimpleEventIsolation(),
        )
        register_handlers(dispatcher)
        await configure_bot_commands(bot, context)
        await dispatcher.start_polling(
            bot,
            context=context,
            allowed_updates=dispatcher.resolve_used_update_types(),
            close_bot_session=False,
        )
    finally:
        if context is not None:
            await shutdown_context(context)
        await bot.session.close()


async def check_environment() -> int:
    settings = load_settings()
    premium = PremiumEmojiRegistry.load(settings.premium_emoji_path)
    ffmpeg = ffmpeg_executable()
    with tempfile.TemporaryDirectory(prefix="emoji-color-check-") as directory:
        database = Database(Path(directory) / "check.db")
        await database.open()
        await database.ensure_owner(1)
        await database.assert_privacy_schema()
        tables = await database.table_names()
        await database.close()
    print(f"Python: {sys.version.split()[0]}")
    print(f"FFmpeg: {ffmpeg.name}")
    print(f"Premium Emoji entries: {premium.loaded_entries}")
    print(f"Premium Emoji mappings: {premium.mappings_available}")
    print(f"SQLite tables: {', '.join(sorted(tables))}")
    print(f"Emoji font: {settings.emoji_font_path or 'not configured'}")
    return 0


def run() -> None:
    parser = argparse.ArgumentParser(description="Emoji & Sticker Color Bot")
    parser.add_argument(
        "--check", action="store_true", help="run offline startup diagnostics without BOT_TOKEN"
    )
    arguments = parser.parse_args()
    if arguments.check:
        raise SystemExit(asyncio.run(check_environment()))
    asyncio.run(run_bot())


if __name__ == "__main__":
    run()
