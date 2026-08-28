"""Telegram-only administrator panel; unauthorized /admin is deliberately silent."""

from __future__ import annotations

import asyncio
import html
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

import psutil
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.context import AppContext
from app.database.settings import maintenance_enabled
from app.keyboards.admin import admin_keyboard
from app.states import AdminStates

router = Router(name="admin")


def _duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


async def _directory_size(path: Path) -> int:
    def calculate() -> int:
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())

    return await asyncio.to_thread(calculate)


async def _dashboard(context: AppContext) -> str:
    stats = await context.database.today_statistics()
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(str(context.settings.temp_root))
    return (
        f'{context.premium.html("ADMIN")} <b>Emoji &amp; Sticker Color Bot — Admin</b>\n\n'
        f"Uptime: {_duration(time.monotonic() - context.started_monotonic)}\n"
        f"Active jobs: {context.jobs.active_count}\nPending jobs: {context.scheduler.pending}\n"
        f"Running workers: {context.scheduler.running}\n\n"
        f"CPU: {psutil.cpu_percent():.1f}%\nRAM: {memory.percent:.1f}%\n"
        f"Disk: {disk.used / disk.total * 100:.1f}%\n"
        f"Temp: {(await _directory_size(context.settings.temp_root)) / 1024 / 1024:.1f} MiB\n\n"
        f"Processed today: {stats.get('jobs_total', 0)}\n"
        f"Successful: {stats.get('jobs_success', 0)}\nFailed: {stats.get('jobs_failed', 0)}\n"
        f"Packs created: {stats.get('emoji_packs_created', 0) + stats.get('sticker_packs_created', 0)}\n"
        f"Telegram 429: {stats.get('telegram_429', 0)}"
    )


@router.message(Command("admin"))
async def admin_command(message: Message, context: AppContext) -> None:
    if message.from_user is None or not await context.admins.is_admin(message.from_user.id):
        return
    owner = await context.admins.is_owner(message.from_user.id)
    await context.ui.answer(
        message,
        await _dashboard(context),
        reply_markup=admin_keyboard(context.premium, owner=owner),
    )


def _admin_action_keyboard(context: AppContext, action: str, label: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"admin:{action}",
                    icon_custom_emoji_id=context.premium.button_id("EDIT"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Назад",
                    callback_data="admin:refresh",
                    icon_custom_emoji_id=context.premium.button_id("BACK"),
                )
            ],
        ]
    )


async def _edit_admin(
    callback: CallbackQuery,
    context: AppContext,
    body: str,
    markup: InlineKeyboardMarkup | None = None,
) -> None:
    if isinstance(callback.message, Message):
        await context.ui.edit(callback.message, body, reply_markup=markup)


@router.callback_query(F.data.startswith("admin:"))
async def admin_callback(
    callback: CallbackQuery, context: AppContext, state: FSMContext
) -> None:
    if not await context.admins.is_admin(callback.from_user.id):
        return
    await callback.answer()
    parts = (callback.data or "").split(":")
    action = parts[1] if len(parts) > 1 else "refresh"
    owner = await context.admins.is_owner(callback.from_user.id)
    if action == "refresh":
        await state.clear()
        await _edit_admin(
            callback,
            context,
            await _dashboard(context),
            admin_keyboard(context.premium, owner=owner),
        )
    elif action == "jobs":
        jobs = context.jobs.active_jobs()
        lines = [f'{context.premium.html("INFO")} <b>Активные задачи</b>']
        rows: list[list[InlineKeyboardButton]] = []
        for job in jobs:
            age = _duration((datetime.now(UTC) - job.created_at).total_seconds())
            lines.append(
                f"\nJob #{job.short_id}\nType: {job.source.kind.value if job.source else 'source'}\n"
                f"Items: {job.total}\nProgress: {job.progress} / {job.total}\n"
                f"State: {job.status.value}\nAge: {age}"
            )
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"Остановить #{job.short_id}",
                        callback_data=f"admin:stop:{job.job_id}",
                        icon_custom_emoji_id=context.premium.button_id("CANCEL"),
                    ),
                    InlineKeyboardButton(
                        text="Остановить и ограничить",
                        callback_data=f"admin:block:{job.job_id}",
                        icon_custom_emoji_id=context.premium.button_id("LOCK"),
                    ),
                ]
            )
        if not jobs:
            lines.append("\nНет активных задач.")
        rows.append(
            [
                InlineKeyboardButton(
                    text="Назад",
                    callback_data="admin:refresh",
                    icon_custom_emoji_id=context.premium.button_id("BACK"),
                )
            ]
        )
        await _edit_admin(
            callback, context, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)
        )
    elif action in {"stop", "block"} and len(parts) == 3:
        target = context.jobs.get(parts[2])
        if target:
            if action == "block":
                context.jobs.temporarily_restrict(target.job_id)
            await context.jobs.cancel(target.job_id)
            if target.created_sets:
                await context.publisher.delete_sets(target.created_sets)
        await _edit_admin(
            callback,
            context,
            await _dashboard(context),
            admin_keyboard(context.premium, owner=owner),
        )
    elif action == "load":
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(str(context.settings.temp_root))
        body = (
            f'{context.premium.html("CPU")} <b>Нагрузка</b>\n\n'
            f"CPU: {psutil.cpu_percent(interval=None):.1f}%\n"
            f"RAM: {memory.percent:.1f}% ({memory.available / 1024 / 1024:.0f} MiB available)\n"
            f"Disk: {disk.free / 1024 / 1024 / 1024:.1f} GiB free\n"
            f"TGS workers: {context.settings.tgs_workers}\n"
            f"Raster workers: {context.settings.raster_workers}\n"
            f"WEBM workers: {context.settings.webm_workers}"
        )
        await _edit_admin(callback, context, body, _admin_action_keyboard(context, "refresh", "Обновить"))
    elif action == "stats":
        stats = await context.database.today_statistics()
        body = f'{context.premium.html("CHART")} <b>Статистика сегодня</b>\n\n' + "\n".join(
            f"{html.escape(key)}: {value}" for key, value in stats.items()
        )
        await _edit_admin(callback, context, body, _admin_action_keyboard(context, "refresh", "Назад"))
    elif action == "telegram":
        body = (
            f'{context.premium.html("LINK")} <b>Telegram API</b>\n\n'
            f"Publishing: {'active' if context.scheduler.accepting else 'stopping'}\n"
            f"Conservative limiter: {'ON' if context.telegram_limiter.enabled else 'OFF'}\n"
            f"Last retry_after: {context.telegram_limiter.last_retry_after or '—'}\n"
            "Bot API target: 10.3"
        )
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Переключить conservative limiter",
                        callback_data="admin:telegram_toggle",
                        icon_custom_emoji_id=context.premium.button_id("SETTINGS"),
                    )
                ],
                [InlineKeyboardButton(text="Назад", callback_data="admin:refresh")],
            ]
        )
        await _edit_admin(callback, context, body, markup)
    elif action == "telegram_toggle":
        context.telegram_limiter.enabled = not context.telegram_limiter.enabled
        await context.database.set_setting(
            "telegram_sticker_conservative_limit_enabled",
            context.telegram_limiter.enabled,
        )
        await _edit_admin(
            callback,
            context,
            f"Conservative limiter: {'ON' if context.telegram_limiter.enabled else 'OFF'}",
            _admin_action_keyboard(context, "telegram", "Назад"),
        )
    elif action == "limits":
        values = context.limits.as_settings()
        body = f'{context.premium.html("SETTINGS")} <b>Лимиты</b>\n\n' + "\n".join(
            f"{key}: {value}" for key, value in values.items()
        )
        if owner:
            body += "\n\nДля изменения отправьте: <code>ключ значение</code>"
            await state.set_state(AdminStates.awaiting_limit)
        await _edit_admin(callback, context, body, _admin_action_keyboard(context, "refresh", "Назад"))
    elif action == "admins" and owner:
        admins = await context.database.list_admins()
        body = f'{context.premium.html("ADMIN")} <b>Администраторы</b>\n\n' + "\n".join(
            f"{role}: <code>{user_id}</code>" for user_id, role in admins
        )
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Добавить",
                        callback_data="admin:add_admin",
                        icon_custom_emoji_id=context.premium.button_id("ADD"),
                    ),
                    InlineKeyboardButton(
                        text="Удалить",
                        callback_data="admin:remove_admin",
                        icon_custom_emoji_id=context.premium.button_id("DELETE"),
                    ),
                ],
                [InlineKeyboardButton(text="Назад", callback_data="admin:refresh")],
            ]
        )
        await _edit_admin(callback, context, body, markup)
    elif action == "add_admin" and owner:
        await state.set_state(AdminStates.awaiting_add_id)
        await _edit_admin(callback, context, "Отправьте numeric Telegram user ID нового администратора.")
    elif action == "remove_admin" and owner:
        await state.set_state(AdminStates.awaiting_remove_id)
        await _edit_admin(callback, context, "Отправьте numeric Telegram user ID администратора.")
    elif action == "errors":
        errors = context.errors.latest()
        body = f'{context.premium.html("WARNING")} <b>Ошибки</b>\n\n'
        if errors:
            body += "\n\n".join(
                f"Job #{item['job_id']}\n{item['component']} | {item['error_type']}\n"
                f"{html.escape(str(item['message']))}"
                for item in errors
            )
        else:
            body += "Ошибок нет."
        await _edit_admin(callback, context, body, _admin_action_keyboard(context, "refresh", "Назад"))
    elif action == "temp":
        active = {job.job_id for job in context.jobs.active_jobs()}
        removed = 0
        for path in context.settings.temp_root.iterdir():
            if path.is_dir() and path.name not in active:
                await asyncio.to_thread(shutil.rmtree, path, True)
                removed += 1
        await _edit_admin(
            callback,
            context,
            f'{context.premium.html("DELETE")} Удалено orphan-каталогов: {removed}',
            _admin_action_keyboard(context, "refresh", "Назад"),
        )
    elif action == "maintenance":
        enabled = not await maintenance_enabled(context.database)
        await context.database.set_setting("maintenance_enabled", enabled)
        await _edit_admin(
            callback,
            context,
            f"Режим обслуживания: {'ON' if enabled else 'OFF'}",
            _admin_action_keyboard(context, "maintenance", "Переключить"),
        )
    elif action == "premium":
        diagnostics = context.premium.diagnostics()
        body = (
            f'{context.premium.html("MAGIC")} <b>Premium Emoji</b>\n\n'
            f"Registry loaded: {diagnostics['loaded']}\n"
            f"Invalid lines: {diagnostics['invalid']}\n"
            f"Mappings available: {diagnostics['mappings']}\n"
            f"Fallback mode: {'ON' if diagnostics['fallback'] else 'OFF'}"
        )
        await _edit_admin(callback, context, body, _admin_action_keyboard(context, "refresh", "Назад"))


@router.message(AdminStates.awaiting_add_id)
async def add_admin_message(message: Message, context: AppContext, state: FSMContext) -> None:
    if message.from_user is None or not await context.admins.is_owner(message.from_user.id):
        await state.clear()
        return
    try:
        target = int((message.text or "").strip())
        await context.admins.add(message.from_user.id, target)
    except (ValueError, PermissionError):
        await message.answer("Некорректный numeric Telegram user ID.")
        return
    await state.clear()
    await message.answer("Администратор добавлен.")


@router.message(AdminStates.awaiting_remove_id)
async def remove_admin_message(message: Message, context: AppContext, state: FSMContext) -> None:
    if message.from_user is None or not await context.admins.is_owner(message.from_user.id):
        await state.clear()
        return
    try:
        target = int((message.text or "").strip())
        removed = await context.admins.remove(message.from_user.id, target)
    except (ValueError, PermissionError):
        await message.answer("Некорректный numeric Telegram user ID.")
        return
    await state.clear()
    await message.answer("Администратор удалён." if removed else "Owner удалить нельзя.")


@router.message(AdminStates.awaiting_limit)
async def limit_message(message: Message, context: AppContext, state: FSMContext) -> None:
    if message.from_user is None or not await context.admins.is_owner(message.from_user.id):
        await state.clear()
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or parts[0] not in context.limits.as_settings():
        await message.answer("Формат: <code>jobs_hour 12</code>")
        return
    try:
        value = int(parts[1])
        if not 1 <= value <= 10000:
            raise ValueError
    except ValueError:
        await message.answer("Значение должно быть целым числом 1..10000.")
        return
    setattr(context.limits, parts[0], value)
    await context.database.set_setting(f"limit.{parts[0]}", value)
    await state.clear()
    await message.answer("Лимит обновлён.")
