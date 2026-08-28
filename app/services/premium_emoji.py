"""Validated Premium Emoji registry loaded exclusively from the supplied TXT file."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger(__name__)
ENTRY_RE = re.compile(
    r"^\s*\d+\)(?P<label>.+?)(?:\s*—\s*|\s+-\s+)(?P<raw_id>.+?)\s*$"
)

SEMANTIC_LABELS: dict[str, tuple[str, str]] = {
    "SUCCESS": ("Подтвердить", "✅"),
    "ERROR": ("Удалить (Вариант 1)", "❌"),
    "WARNING": ("Предупреждение", "❗"),
    "COLOR": ("Пипетка", "🎨"),
    "BACK": ("Стрелка влево", "⬅️"),
    "CANCEL": ("Отмена", "❌"),
    "LOADING": ("Анимированная загрузка", "⌛"),
    "DOWNLOAD": ("Скачать на устройство", "⬇️"),
    "UPLOAD": ("Загрузить вверх", "⬆️"),
    "PACK": ("Архив", "📦"),
    "ADMIN": ("Пользователи со значком Premium", "👥"),
    "FILE": ("Файл", "📁"),
    "ZIP": ("Скачать из архива", "🗜️"),
    "STICKER": ("Добавить стикер", "🙂"),
    "EMOJI": ("Добавить смайлик", "😀"),
    "REFRESH": ("Обновить", "🔄"),
    "INFO": ("Информация", "ℹ️"),
    "HELP": ("Помощь", "❓"),
    "SETTINGS": ("Настройки 1", "⚙️"),
    "DELETE": ("Удалить (Вариант 2)", "🗑️"),
    "ADD": ("Ещё", "➕"),
    "EDIT": ("Редактировать", "✏️"),
    "PREVIEW": ("Просмотреть", "👁"),
    "LINK": ("Ссылка", "🔗"),
    "LANGUAGE": ("Перевод", "🌐"),
    "FLAG_RU": ("🇷🇺", "🇷🇺"),
    "FLAG_EN": ("🇺🇸", "🇺🇸"),
    "CHART": ("Столбчатая диаграмма", "📊"),
    "CPU": ("Ноутбук", "💻"),
    "RAM": ("Куб", "🧊"),
    "DISK": ("Папка (Вариант 1)", "📂"),
    "LOCK": ("Заблокировано", "🔒"),
    "UNLOCK": ("Разблокировано", "🔓"),
    "MAGIC": ("Волшебная палочка", "🪄"),
    "BRUSH": ("Волшебная кисть", "🖌"),
    "HOME": ("Дом с дверью", "🏠"),
    "TIME": ("Секундомер", "⏱"),
    "BOT": ("Бот", "🤖"),
}


@dataclass(frozen=True, slots=True)
class PremiumIcon:
    custom_emoji_id: str | None
    fallback: str

    def html(self) -> str:
        if self.custom_emoji_id:
            return f'<tg-emoji emoji-id="{self.custom_emoji_id}">{self.fallback}</tg-emoji>'
        return self.fallback


class PremiumEmojiRegistry:
    def __init__(self, source: Path) -> None:
        self.source = source
        self.loaded_entries = 0
        self.invalid_entries = 0
        self.enabled = True
        self._icons: dict[str, PremiumIcon] = {
            key: PremiumIcon(None, fallback) for key, (_, fallback) in SEMANTIC_LABELS.items()
        }

    @classmethod
    def load(cls, source: Path) -> PremiumEmojiRegistry:
        registry = cls(source)
        if not source.is_file():
            LOGGER.warning("Premium Emoji registry is missing; fallback mode enabled")
            registry.enabled = False
            return registry
        labels: dict[str, str] = {}
        for line in source.read_text(encoding="utf-8-sig").splitlines():
            match = ENTRY_RE.match(line)
            if not match:
                if line.strip():
                    registry.invalid_entries += 1
                continue
            label = match.group("label").strip()
            raw_id = match.group("raw_id")
            clean_id = "".join(char for char in raw_id if char.isdecimal())
            clean_id = "".join(str(unicodedata.digit(char)) for char in clean_id)
            if not (16 <= len(clean_id) <= 20):
                registry.invalid_entries += 1
                continue
            labels[label] = clean_id
            registry.loaded_entries += 1
        for key, (needle, fallback) in SEMANTIC_LABELS.items():
            emoji_id = next((value for label, value in labels.items() if needle in label), None)
            registry._icons[key] = PremiumIcon(emoji_id, fallback)
            if emoji_id is None:
                LOGGER.warning("Premium Emoji semantic mapping missing: %s", key)
        return registry

    def icon(self, key: str) -> PremiumIcon:
        return self._icons.get(key, PremiumIcon(None, "•"))

    def html(self, key: str) -> str:
        icon = self.icon(key)
        return icon.html() if self.enabled else icon.fallback

    def button_id(self, key: str) -> str | None:
        return self.icon(key).custom_emoji_id if self.enabled else None

    def disable(self) -> None:
        if self.enabled:
            LOGGER.warning("Telegram rejected Premium Emoji UI; runtime fallback enabled")
        self.enabled = False

    @property
    def mappings_available(self) -> int:
        return sum(icon.custom_emoji_id is not None for icon in self._icons.values())

    def diagnostics(self) -> dict[str, object]:
        return {
            "loaded": self.loaded_entries,
            "invalid": self.invalid_entries,
            "mappings": self.mappings_available,
            "fallback": not self.enabled,
        }
