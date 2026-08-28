"""Public commands and RAM-only language selection."""

from __future__ import annotations

import contextlib

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from app.context import AppContext
from app.i18n import language_for, text
from app.keyboards.user import language_keyboard

router = Router(name="commands")


def current_language(message: Message, context: AppContext) -> str:
    if message.from_user is None:
        return "en"
    return context.languages.get(
        message.from_user.id, language_for(message.from_user.language_code)
    )


@router.message(CommandStart())
async def start(message: Message, context: AppContext) -> None:
    if message.chat.type != "private":
        await message.answer("Open Emoji & Sticker Color Bot in a private chat.")
        return
    language = current_language(message, context)
    await context.ui.answer(
        message,
        text(language, "start", icon=context.premium.html("BRUSH")),
    )


@router.message(Command("help"))
async def help_command(message: Message, context: AppContext) -> None:
    if message.chat.type != "private":
        return
    language = current_language(message, context)
    await context.ui.answer(
        message,
        text(language, "help", icon=context.premium.html("HELP")),
    )


@router.message(Command("privacy"))
async def privacy_command(message: Message, context: AppContext) -> None:
    if message.chat.type != "private":
        return
    language = current_language(message, context)
    await context.ui.answer(
        message,
        text(language, "privacy", icon=context.premium.html("LOCK")),
    )


@router.message(Command("colors"))
async def colors_command(message: Message, context: AppContext) -> None:
    if message.chat.type != "private":
        return
    language = current_language(message, context)
    await context.ui.answer(
        message,
        text(language, "colors", icon=context.premium.html("COLOR")),
    )


@router.message(Command("language"))
async def language_command(message: Message, context: AppContext) -> None:
    if message.chat.type != "private":
        return
    language = current_language(message, context)
    await context.ui.answer(
        message,
        text(language, "language", icon=context.premium.html("LANGUAGE")),
        reply_markup=language_keyboard(context.premium),
    )


@router.callback_query(F.data.startswith("lang:"))
async def language_callback(callback: CallbackQuery, context: AppContext) -> None:
    if callback.from_user is None or callback.message is None:
        return
    language = (callback.data or "").partition(":")[2]
    if language not in {"ru", "en"}:
        return
    context.languages[callback.from_user.id] = language
    await callback.answer()
    if isinstance(callback.message, Message):
        await context.ui.edit(
            callback.message,
            text(language, "language_changed", icon=context.premium.html("SUCCESS")),
        )


@router.message(Command("cancel"))
async def cancel_command(message: Message, context: AppContext) -> None:
    if message.from_user is None or message.chat.type != "private":
        return
    language = current_language(message, context)
    jobs = sorted(context.jobs.for_user(message.from_user.id), key=lambda item: item.created_at)
    if not jobs:
        await context.ui.answer(
            message,
            f'{context.premium.html("INFO")} {text(language, "nothing_to_cancel")}',
        )
        return
    current = jobs[-1]
    if current.control_message_id is not None:
        with contextlib.suppress(Exception):
            await context.bot.edit_message_reply_markup(
                chat_id=current.chat_id,
                message_id=current.control_message_id,
                reply_markup=None,
            )
    job = await context.jobs.cancel(current.job_id)
    if job and job.created_sets:
        await context.publisher.delete_sets(job.created_sets)
    await context.ui.answer(
        message,
        text(language, "cancelled", icon=context.premium.html("CANCEL")),
    )
