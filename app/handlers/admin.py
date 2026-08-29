"""Telegram-only administrator panel; unauthorized /admin is deliberately silent."""

from __future__ import annotations

import asyncio
import html
import logging
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
from app.handlers.commands import show_main_menu
from app.keyboards.admin import admin_keyboard
from app.states import AdminStates

router = Router(name="admin")
LOGGER = logging.getLogger(__name__)


def _duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _switch(value: bool) -> str:
    return "включён" if value else "выключен"


STAT_LABELS = {
    "jobs_total": "Всего задач",
    "jobs_success": "Успешно",
    "jobs_failed": "С ошибкой",
    "items_processed": "Обработано элементов",
    "tgs_processed": "TGS",
    "webm_processed": "WEBM",
    "raster_processed": "PNG / WEBP",
    "emoji_packs_created": "Emoji-наборов",
    "sticker_packs_created": "Наборов стикеров",
    "telegram_429": "Ограничений Telegram",
    "processing_ms_total": "Время обработки, мс",
}

LIMIT_LABELS = {
    "jobs_10_minutes": "Задач за 10 минут",
    "jobs_hour": "Задач за час",
    "jobs_day": "Задач за сутки",
    "large_hour": "Крупных задач за час",
    "large_day": "Крупных задач за сутки",
    "huge_hour": "Очень крупных задач за час",
    "huge_day": "Очень крупных задач за сутки",
    "heavy_webm_hour": "Тяжёлых WEBM за час",
    "heavy_webm_day": "Тяжёлых WEBM за сутки",
}

SOURCE_LABELS = {
    "sticker": "Стикер",
    "custom_emoji": "Custom Emoji",
    "pack": "Telegram-набор",
    "file": "Файл",
    "zip": "ZIP-архив",
    "unicode": "Unicode Emoji",
    "media_group": "Группа файлов",
}

STATUS_LABELS = {
    "source_analysis": "Анализ источника",
    "awaiting_color": "Ожидание цвета",
    "generating_preview": "Создание предпросмотра",
    "awaiting_preview_decision": "Ожидание подтверждения",
    "awaiting_output_type": "Выбор результата",
    "awaiting_pack_name": "Ожидание названия",
    "awaiting_split_confirmation": "Ожидание разделения",
    "awaiting_result_action": "Ожидание действия с результатом",
    "processing": "Обработка",
    "download": "Скачивание файла",
    "publishing": "Публикация",
    "completed": "Завершено",
    "cancelled": "Отменено",
    "failed": "Ошибка",
}

COMPONENT_LABELS = {
    "source": "Источник",
    "preview": "Предпросмотр",
    "adaptive_preview": "Предпросмотр Adaptive",
    "processing": "Обработка",
}


async def _directory_size(path: Path) -> int:
    def calculate() -> int:
        total = 0
        for item in path.rglob("*"):
            try:
                if item.is_file():
                    total += item.stat().st_size
            except OSError:
                continue
        return total

    return await asyncio.to_thread(calculate)


async def _dashboard(context: AppContext) -> str:
    stats = await context.database.today_statistics()
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(str(context.settings.temp_root))
    return (
        f'{context.premium.html("ADMIN")} <b>Панель администратора</b>\n\n'
        "<blockquote>"
        f'{context.premium.html("TIME")} <b>Состояние сервиса</b>\n'
        f"Время работы: <code>{_duration(time.monotonic() - context.started_monotonic)}</code>\n"
        f"Активные задачи: <b>{context.jobs.active_count}</b>\n"
        f"В очереди: <b>{context.scheduler.pending}</b>\n"
        f"Занятые обработчики: <b>{context.scheduler.running}</b>"
        "</blockquote>\n\n"
        "<blockquote>"
        f'{context.premium.html("CPU")} <b>Ресурсы сервера</b>\n'
        f"Процессор: <b>{psutil.cpu_percent():.1f}%</b>\n"
        f"Оперативная память: <b>{memory.percent:.1f}%</b>\n"
        f"Диск: <b>{disk.used / disk.total * 100:.1f}%</b>\n"
        f"Временные файлы: <b>{(await _directory_size(context.settings.temp_root)) / 1024 / 1024:.1f} МиБ</b>"
        "</blockquote>\n\n"
        "<blockquote>"
        f'{context.premium.html("CHART")} <b>Статистика за сегодня</b>\n'
        f"Всего задач: <b>{stats.get('jobs_total', 0)}</b>\n"
        f"Успешно: <b>{stats.get('jobs_success', 0)}</b>\n"
        f"С ошибкой: <b>{stats.get('jobs_failed', 0)}</b>\n"
        "Создано наборов: "
        f"<b>{stats.get('emoji_packs_created', 0) + stats.get('sticker_packs_created', 0)}</b>\n"
        f"Ограничений Telegram: <b>{stats.get('telegram_429', 0)}</b>"
        "</blockquote>"
    )


async def _safe_dashboard(context: AppContext) -> str:
    try:
        return await _dashboard(context)
    except Exception as error:
        LOGGER.warning("Admin dashboard metrics unavailable | %s", type(error).__name__)
        return (
            f'{context.premium.html("ADMIN")} '
            "<b>Панель администратора</b>\n\n"
            "<blockquote>Панель доступна, но часть показателей сервера временно "
            "недоступна. Нажмите «Обновить» через несколько секунд.</blockquote>"
        )


@router.message(Command("admin"))
async def admin_command(message: Message, context: AppContext) -> None:
    if message.from_user is None:
        return
    user_id = message.from_user.id
    owner_id = context.admins.owner_id
    if user_id != owner_id and not await context.admins.is_admin(user_id):
        return
    owner = user_id == owner_id
    await context.ui.answer(
        message,
        await _safe_dashboard(context),
        reply_markup=admin_keyboard(context.premium, owner=owner),
    )


def _admin_action_keyboard(context: AppContext, action: str, label: str) -> InlineKeyboardMarkup:
    if label == "Назад":
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Назад",
                        callback_data=f"admin:{action}",
                        icon_custom_emoji_id=context.premium.button_id("BACK"),
                    )
                ]
            ]
        )
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


def _admin_back_keyboard(
    context: AppContext, action: str = "refresh"
) -> InlineKeyboardMarkup:
    return _admin_action_keyboard(context, action, "Назад")


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
    await state.clear()
    if action == "refresh":
        await state.clear()
        await _edit_admin(
            callback,
            context,
            await _safe_dashboard(context),
            admin_keyboard(context.premium, owner=owner),
        )
    elif action == "close":
        await state.clear()
        language = context.languages.get(callback.from_user.id)
        if language is None:
            language = await context.admins.language(callback.from_user.id)
            context.languages[callback.from_user.id] = language
        if isinstance(callback.message, Message):
            await show_main_menu(callback.message, context, language)
    elif action == "jobs":
        jobs = context.jobs.active_jobs()
        lines = [f'{context.premium.html("INFO")} <b>Активные задачи</b>']
        rows: list[list[InlineKeyboardButton]] = []
        for job in jobs:
            age = _duration((datetime.now(UTC) - job.created_at).total_seconds())
            source = job.source.kind.value if job.source else "source"
            lines.append(
                f'\n{context.premium.html("LOADING")} <b>Задача #{job.short_id}</b>\n'
                f'{context.premium.html("FILE")} Тип: '
                f"{SOURCE_LABELS.get(source, 'Источник')}\n"
                f'{context.premium.html("PACK")} Элементов: {job.total}\n'
                f'{context.premium.html("CHART")} Ход выполнения: '
                f"{job.progress} / {job.total}\n"
                f'{context.premium.html("INFO")} Состояние: '
                f"{STATUS_LABELS.get(job.status.value, 'Неизвестно')}\n"
                f'{context.premium.html("TIME")} Выполняется: {age}'
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
            await _safe_dashboard(context),
            admin_keyboard(context.premium, owner=owner),
        )
    elif action == "load":
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(str(context.settings.temp_root))
        body = (
            f'{context.premium.html("CPU")} <b>Нагрузка</b>\n\n'
            "<blockquote>"
            f'{context.premium.html("CPU")} CPU: {psutil.cpu_percent(interval=None):.1f}%\n'
            f'{context.premium.html("RAM")} Оперативная память: {memory.percent:.1f}% '
            f"({memory.available / 1024 / 1024:.0f} МиБ свободно)\n"
            f'{context.premium.html("DISK")} Диск: '
            f"{disk.free / 1024 / 1024 / 1024:.1f} ГиБ свободно\n"
            f'{context.premium.html("SETTINGS")} Обработчики TGS: '
            f"{context.settings.tgs_workers}\n"
            f'{context.premium.html("SETTINGS")} Обработчики изображений: '
            f"{context.settings.raster_workers}\n"
            f'{context.premium.html("SETTINGS")} Обработчики WEBM: '
            f"{context.settings.webm_workers}</blockquote>"
        )
        await _edit_admin(callback, context, body, _admin_action_keyboard(context, "load", "Обновить"))
    elif action == "stats":
        stats = await context.database.today_statistics()
        body = f'{context.premium.html("CHART")} <b>Статистика сегодня</b>\n\n' + "\n".join(
            f"{STAT_LABELS.get(key, html.escape(key))}: <b>{value}</b>"
            for key, value in stats.items()
        )
        await _edit_admin(callback, context, body, _admin_action_keyboard(context, "refresh", "Назад"))
    elif action == "telegram":
        body = (
            f'{context.premium.html("LINK")} <b>Telegram API</b>\n\n'
            "<blockquote>"
            f'{context.premium.html("UPLOAD")} Публикация: '
            f"{'активна' if context.scheduler.accepting else 'останавливается'}\n"
            f'{context.premium.html("SETTINGS")} Предварительный ограничитель: '
            f"{_switch(context.telegram_limiter.enabled)}\n"
            f'{context.premium.html("TIME")} Последнее ожидание Telegram: '
            f"{context.telegram_limiter.last_retry_after or '—'} с\n"
            f'{context.premium.html("CHART")} Предварительное окно: '
            f"{context.telegram_limiter.requests} запросов / "
            f"{context.telegram_limiter.window} с\n"
            f'{context.premium.html("BOT")} Версия Bot API: 10.3'
            "</blockquote>\n\n"
            "Предварительный режим ограничивает число запросов, а не число эмодзи. "
            "Он необязателен. Ответ <code>retry_after</code> от Telegram всегда имеет "
            "приоритет: бот показывает таймер и продолжает ту же операцию автоматически."
        )
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Переключить ограничитель",
                        callback_data="admin:telegram_toggle",
                        icon_custom_emoji_id=context.premium.button_id("SETTINGS"),
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
            f"Предварительный ограничитель {_switch(context.telegram_limiter.enabled)}.",
            _admin_action_keyboard(context, "telegram", "Назад"),
        )
    elif action == "limits":
        values = context.limits.as_settings()
        body = f'{context.premium.html("SETTINGS")} <b>Лимиты</b>\n\n' + "\n".join(
            f"{LIMIT_LABELS.get(key, key)}: <b>{value}</b> "
            f"(<code>{key}</code>)"
            for key, value in values.items()
        )
        if owner:
            body += "\n\nДля изменения отправьте: <code>ключ значение</code>"
            await state.set_state(AdminStates.awaiting_limit)
        await _edit_admin(callback, context, body, _admin_action_keyboard(context, "refresh", "Назад"))
    elif action == "admins" and owner:
        admins = await context.database.list_admins()
        body = f'{context.premium.html("ADMIN")} <b>Администраторы</b>\n\n' + "\n".join(
            f"{'Владелец' if role == 'owner' else 'Администратор'}: "
            f"<code>{user_id}</code>"
            for user_id, role in admins
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
                [
                    InlineKeyboardButton(
                        text="Назад",
                        callback_data="admin:refresh",
                        icon_custom_emoji_id=context.premium.button_id("BACK"),
                    )
                ],
            ]
        )
        await _edit_admin(callback, context, body, markup)
    elif action == "add_admin" and owner:
        await state.set_state(AdminStates.awaiting_add_id)
        await _edit_admin(
            callback,
            context,
            f'{context.premium.html("ADD")} <b>Добавление администратора</b>\n\n'
            "<blockquote>Отправьте числовой Telegram ID нового администратора.</blockquote>",
            _admin_back_keyboard(context, "admins"),
        )
    elif action == "remove_admin" and owner:
        await state.set_state(AdminStates.awaiting_remove_id)
        await _edit_admin(
            callback,
            context,
            f'{context.premium.html("DELETE")} <b>Удаление администратора</b>\n\n'
            "<blockquote>Отправьте числовой Telegram ID администратора.</blockquote>",
            _admin_back_keyboard(context, "admins"),
        )
    elif action == "errors":
        errors = context.errors.latest()
        body = f'{context.premium.html("WARNING")} <b>Ошибки</b>\n\n'
        if errors:
            body += "\n\n".join(
                f"Задача #{item['job_id']}\n"
                f"{COMPONENT_LABELS.get(str(item['component']), 'Система')} | "
                f"{item['error_type']}\n"
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
            f'{context.premium.html("DELETE")} Удалено неиспользуемых каталогов: {removed}',
            _admin_action_keyboard(context, "refresh", "Назад"),
        )
    elif action == "maintenance":
        enabled = not await maintenance_enabled(context.database)
        await context.database.set_setting("maintenance_enabled", enabled)
        await _edit_admin(
            callback,
            context,
            f"Режим обслуживания {_switch(enabled)}.",
            _admin_action_keyboard(context, "maintenance", "Переключить"),
        )
    elif action == "premium":
        diagnostics = context.premium.diagnostics()
        body = (
            f'{context.premium.html("MAGIC")} <b>Premium Emoji</b>\n\n'
            f"Загружено записей: {diagnostics['loaded']}\n"
            f"Некорректных строк: {diagnostics['invalid']}\n"
            f"Доступно сопоставлений: {diagnostics['mappings']}\n"
            f"Резервный режим: {_switch(bool(diagnostics['fallback']))}"
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
        await message.answer(
            f'{context.premium.html("ERROR")} Укажите корректный числовой Telegram ID.',
            reply_markup=_admin_back_keyboard(context, "admins"),
        )
        return
    await state.clear()
    await message.answer(
        f'{context.premium.html("SUCCESS")} Администратор добавлен.',
        reply_markup=_admin_back_keyboard(context, "admins"),
    )


@router.message(AdminStates.awaiting_remove_id)
async def remove_admin_message(message: Message, context: AppContext, state: FSMContext) -> None:
    if message.from_user is None or not await context.admins.is_owner(message.from_user.id):
        await state.clear()
        return
    try:
        target = int((message.text or "").strip())
        removed = await context.admins.remove(message.from_user.id, target)
    except (ValueError, PermissionError):
        await message.answer(
            f'{context.premium.html("ERROR")} Укажите корректный числовой Telegram ID.',
            reply_markup=_admin_back_keyboard(context, "admins"),
        )
        return
    await state.clear()
    icon = "SUCCESS" if removed else "WARNING"
    await message.answer(
        f'{context.premium.html(icon)} '
        + ("Администратор удалён." if removed else "Владельца удалить нельзя."),
        reply_markup=_admin_back_keyboard(context, "admins"),
    )


@router.message(AdminStates.awaiting_limit)
async def limit_message(message: Message, context: AppContext, state: FSMContext) -> None:
    if message.from_user is None or not await context.admins.is_owner(message.from_user.id):
        await state.clear()
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or parts[0] not in context.limits.as_settings():
        await message.answer(
            f'{context.premium.html("INFO")} Формат: <code>jobs_hour 12</code>',
            reply_markup=_admin_back_keyboard(context),
        )
        return
    try:
        value = int(parts[1])
        if not 1 <= value <= 10000:
            raise ValueError
    except ValueError:
        await message.answer(
            f'{context.premium.html("ERROR")} Значение должно быть целым числом 1..10000.',
            reply_markup=_admin_back_keyboard(context),
        )
        return
    setattr(context.limits, parts[0], value)
    await context.database.set_setting(f"limit.{parts[0]}", value)
    await state.clear()
    await message.answer(
        f'{context.premium.html("SUCCESS")} Лимит обновлён.',
        reply_markup=_admin_back_keyboard(context),
    )
