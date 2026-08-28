"""Sanitizing application logging that excludes Telegram user data."""

from __future__ import annotations

import logging
import logging.handlers
import re
from pathlib import Path
from typing import Any

LONG_NUMBER = re.compile(r"(?<![A-Za-z0-9])[+-]?\d{5,}(?![A-Za-z0-9])")
BOT_TOKEN = re.compile(r"\b\d{5,}:[A-Za-z0-9_-]{20,}\b")
WINDOWS_PATH = re.compile(r"[A-Za-z]:\\[^\s|]+")
UNIX_PATH = re.compile(r"(?<![:\w])/(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+")
SENSITIVE_FIELD = re.compile(
    r"(?i)\b(chat_id|user_id|file_id|custom_emoji_id|username|first_name|last_name|title|name)"
    r"\s*[=:]\s*(['\"]?)[^\s,|)}\]]+\2"
)


def sanitize_text(value: object) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = BOT_TOKEN.sub("<token>", text)
    text = WINDOWS_PATH.sub("<path>", text)
    text = UNIX_PATH.sub("<path>", text)
    text = SENSITIVE_FIELD.sub(lambda match: f"{match.group(1)}=<redacted>", text)
    return LONG_NUMBER.sub("<id>", text)[:1000]


class PrivacyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = sanitize_text(record.getMessage())
        record.args = ()
        return True


def configure_logging(log_dir: Path, level: str = "INFO") -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    privacy = PrivacyFilter()
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    stream.addFilter(privacy)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "app.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(privacy)
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level.upper())
    root.addHandler(stream)
    root.addHandler(file_handler)
    # Prevent framework INFO logs from serializing Update details; warnings remain filtered.
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


def safe_error(logger: logging.Logger, component: str, error: BaseException, job_id: str) -> None:
    logger.error(
        "JOB %s | %s | %s | %s",
        job_id[:6],
        sanitize_text(component),
        type(error).__name__,
        sanitize_text(error),
    )


class ErrorBuffer:
    """Bounded, anonymized runtime errors for the Telegram admin panel."""

    def __init__(self, maximum: int = 100) -> None:
        self.maximum = maximum
        self._items: list[dict[str, Any]] = []

    def add(self, *, job_id: str, component: str, error: BaseException) -> None:
        self._items.append(
            {
                "job_id": job_id[:6].upper(),
                "component": sanitize_text(component),
                "error_type": type(error).__name__,
                "message": sanitize_text(error),
            }
        )
        del self._items[: max(0, len(self._items) - self.maximum)]

    def latest(self, limit: int = 10) -> list[dict[str, Any]]:
        return list(reversed(self._items[-limit:]))
