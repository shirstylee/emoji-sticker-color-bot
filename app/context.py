"""Explicit dependency container passed to aiogram handlers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from aiogram import Bot

from app.config import Settings
from app.database.admins import AdminService
from app.database.connection import Database
from app.logging import ErrorBuffer
from app.models.limits import LimitsConfig
from app.services.jobs import JobManager
from app.services.media_groups import MediaGroupCollector
from app.services.pipeline import ProcessingPipeline
from app.services.premium_emoji import PremiumEmojiRegistry
from app.services.scheduler import JobScheduler
from app.services.telegram_rate_limiter import TelegramStickerRateController
from app.services.telegram_stickers import StickerPublisher
from app.services.ui import SafeUI
from app.services.user_rate_limiter import UserRateLimiter


@dataclass(slots=True)
class AppContext:
    bot: Bot
    bot_username: str
    settings: Settings
    database: Database
    admins: AdminService
    jobs: JobManager
    scheduler: JobScheduler
    pipeline: ProcessingPipeline
    user_limiter: UserRateLimiter
    telegram_limiter: TelegramStickerRateController
    publisher: StickerPublisher
    premium: PremiumEmojiRegistry
    ui: SafeUI
    media_groups: MediaGroupCollector
    limits: LimitsConfig
    errors: ErrorBuffer = field(default_factory=ErrorBuffer)
    languages: dict[int, str] = field(default_factory=dict)
    menu_messages: dict[int, tuple[int, int]] = field(default_factory=dict)
    started_monotonic: float = field(default_factory=time.monotonic)
    shutdown_requested: bool = False
