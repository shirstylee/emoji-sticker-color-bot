"""Telegram-only admin dashboard keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.services.premium_emoji import PremiumEmojiRegistry


def admin_keyboard(registry: PremiumEmojiRegistry, *, owner: bool) -> InlineKeyboardMarkup:
    def button(icon: str, label: str, action: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=label,
            callback_data=f"admin:{action}",
            icon_custom_emoji_id=registry.button_id(icon),
        )

    rows = [
        [button("REFRESH", "Обновить", "refresh"), button("INFO", "Активные задачи", "jobs")],
        [button("CPU", "Нагрузка", "load"), button("CHART", "Статистика", "stats")],
        [button("LINK", "Telegram API", "telegram"), button("SETTINGS", "Лимиты", "limits")],
        [button("WARNING", "Ошибки", "errors"), button("DELETE", "Очистить Temp", "temp")],
        [button("LOCK", "Режим обслуживания", "maintenance")],
    ]
    if owner:
        rows.insert(3, [button("ADMIN", "Администраторы", "admins")])
    rows.append([button("MAGIC", "Premium Emoji", "premium")])
    rows.append([button("BACK", "Назад", "close")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
