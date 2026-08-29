"""Environment-backed application configuration."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.constants import MIB


class Settings(BaseSettings):
    """Settings contain no ordinary-user persistent data."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str = ""
    owner_id: int = 0
    color_picker_url: str = "https://htmlcolorcodes.com/color-picker/"
    database_path: Path = Path("data/bot.db")
    temp_root: Path = Path("temp/jobs")
    premium_emoji_path: Path = Path("Main.txt")
    emoji_font_path: Path | None = None
    log_dir: Path = Path("logs")
    log_level: str = "INFO"

    max_input_download_mib: int = 19
    max_zip_extracted_mib: int = 128
    max_zip_files: int = 200
    max_media_group_files: int = 50
    max_logical_items: int = 200
    max_raster_dimension: int = 4096
    max_raster_pixels: int = 16_000_000
    max_tgs_json_mib: int = 5
    max_output_zip_part_mib: int = 45
    job_idle_timeout_seconds: int = 900
    ffmpeg_timeout_seconds: int = 180

    global_pending_regular: int = 30
    ram_safety_min_mib: int = 768
    disk_safety_min_mib: int = 2048

    telegram_sticker_conservative_limit_enabled: bool = True
    telegram_sticker_conservative_requests: int = 8
    telegram_sticker_conservative_window_seconds: int = 240

    global_running_jobs: int = Field(default_factory=lambda: min(max((os.cpu_count() or 2) * 2, 4), 12))
    tgs_workers: int = Field(default_factory=lambda: min(max(os.cpu_count() or 2, 2), 6))
    raster_workers: int = Field(
        default_factory=lambda: min(max((os.cpu_count() or 2) // 2, 2), 4)
    )
    webm_workers: int = Field(default_factory=lambda: 2 if (os.cpu_count() or 2) > 4 else 1)
    archive_workers: int = 2
    preview_workers: int = 4

    @property
    def max_input_download(self) -> int:
        return self.max_input_download_mib * MIB

    @property
    def max_zip_extracted(self) -> int:
        return self.max_zip_extracted_mib * MIB

    @property
    def max_tgs_json(self) -> int:
        return self.max_tgs_json_mib * MIB

    @property
    def max_output_zip_part(self) -> int:
        return self.max_output_zip_part_mib * MIB

    def validate_runtime(self) -> None:
        if sys.version_info < (3, 12):
            raise RuntimeError("Python 3.12 or newer is required")
        if not self.bot_token or ":" not in self.bot_token:
            raise RuntimeError("BOT_TOKEN is missing or malformed")
        if self.owner_id <= 0:
            raise RuntimeError("OWNER_ID must be a positive Telegram numeric user ID")


def discover_emoji_font(configured: Path | None = None) -> Path | None:
    """Locate a configured/system color emoji font without downloading assets."""

    candidates: list[Path] = []
    if configured:
        candidates.append(configured)
    if sys.platform == "win32":
        windows = Path(os.environ.get("WINDIR", "C:/Windows"))
        candidates.append(windows / "Fonts" / "seguiemj.ttf")
    else:
        candidates.extend(
            [
                Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
                Path("/usr/share/fonts/noto/NotoColorEmoji.ttf"),
                Path("/usr/local/share/fonts/NotoColorEmoji.ttf"),
            ]
        )
    return next((path.resolve() for path in candidates if path.is_file()), None)
