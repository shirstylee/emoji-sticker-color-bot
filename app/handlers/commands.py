"""Public commands and persistent administrator language selection."""

from __future__ import annotations

import contextlib
import html

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from app.context import AppContext
from app.i18n import text
from app.keyboards.user import (
    language_keyboard,
    main_menu_keyboard,
    menu_back_keyboard,
    packs_keyboard,
)

router = Router(name="commands")


def current_language(
    message: Message, context: AppContext, *, is_admin: bool = False
) -> str:
    if message.from_user is None:
        return "ru"
    if not is_admin:
        return "ru"
    return context.languages.get(message.from_user.id, "ru")


async def _delete_previous_menu(
    context: AppContext, user_id: int, *, keep_message_id: int | None = None
) -> None:
    previous = context.menu_messages.pop(user_id, None)
    if previous is None or previous[1] == keep_message_id:
        return
    with contextlib.suppress(Exception):
        await context.bot.delete_message(previous[0], previous[1])


async def show_main_menu(
    message: Message, context: AppContext, language: str
) -> Message | bool:
    is_admin = await context.admins.is_admin(message.chat.id)
    if not is_admin:
        language = "ru"
        context.languages.pop(message.chat.id, None)
    await _delete_previous_menu(context, message.chat.id, keep_message_id=message.message_id)
    result = await context.ui.edit(
        message,
        text(
            language,
            "main_menu",
            icon=context.premium.html("BRUSH"),
            **context.premium.placeholders(),
        ),
        reply_markup=main_menu_keyboard(context.premium, language, is_admin=is_admin),
    )
    context.menu_messages[message.chat.id] = (message.chat.id, message.message_id)
    return result


@router.message(CommandStart())
async def start(message: Message, context: AppContext) -> None:
    if message.chat.type != "private":
        await message.answer("Open Emoji & Sticker Color Bot in a private chat.")
        return
    if message.from_user is None:
        return
    await _delete_previous_menu(context, message.from_user.id)
    is_admin = await context.admins.is_admin(message.from_user.id)
    if is_admin:
        language = current_language(message, context, is_admin=True)
        sent = await context.ui.answer(
            message,
            text(
                language,
                "main_menu",
                icon=context.premium.html("BRUSH"),
                **context.premium.placeholders(),
            ),
            reply_markup=main_menu_keyboard(
                context.premium, language, is_admin=True
            ),
        )
    else:
        context.languages.pop(message.from_user.id, None)
        sent = await context.ui.answer(
            message,
            text(
                "ru",
                "main_menu",
                icon=context.premium.html("BRUSH"),
                **context.premium.placeholders(),
            ),
            reply_markup=main_menu_keyboard(context.premium, "ru", is_admin=False),
        )
    context.menu_messages[message.from_user.id] = (message.chat.id, sent.message_id)
    with contextlib.suppress(Exception):
        await message.delete()


@router.message(Command("help"))
async def help_command(message: Message, context: AppContext) -> None:
    if message.chat.type != "private":
        return
    if message.from_user is None:
        return
    is_admin = await context.admins.is_admin(message.from_user.id)
    language = current_language(message, context, is_admin=is_admin)
    await context.ui.answer(
        message,
        text(language, "help", icon=context.premium.html("HELP")),
    )


@router.message(Command("colors"))
async def colors_command(message: Message, context: AppContext) -> None:
    if message.chat.type != "private":
        return
    if message.from_user is None:
        return
    is_admin = await context.admins.is_admin(message.from_user.id)
    language = current_language(message, context, is_admin=is_admin)
    await context.ui.answer(
        message,
        text(language, "colors", icon=context.premium.html("COLOR")),
    )


@router.message(Command("language"))
async def language_command(message: Message, context: AppContext) -> None:
    if message.chat.type != "private":
        return
    if message.from_user is None:
        return
    is_admin = await context.admins.is_admin(message.from_user.id)
    if not is_admin:
        context.languages.pop(message.from_user.id, None)
        return
    language = current_language(message, context, is_admin=True)
    sent = await context.ui.answer(
        message,
        text(language, "language", icon=context.premium.html("LANGUAGE")),
        reply_markup=language_keyboard(context.premium),
    )
    if message.from_user is not None:
        await _delete_previous_menu(context, message.from_user.id)
        context.menu_messages[message.from_user.id] = (message.chat.id, sent.message_id)


@router.callback_query(F.data.startswith("lang:"))
async def language_callback(callback: CallbackQuery, context: AppContext) -> None:
    if callback.from_user is None or callback.message is None:
        return
    if not await context.admins.is_admin(callback.from_user.id):
        context.languages.pop(callback.from_user.id, None)
        await callback.answer()
        if isinstance(callback.message, Message):
            await show_main_menu(callback.message, context, "ru")
        return
    language = (callback.data or "").partition(":")[2]
    if language not in {"ru", "en"}:
        return
    context.languages[callback.from_user.id] = language
    await context.admins.set_language(callback.from_user.id, language)
    await callback.answer()
    if isinstance(callback.message, Message):
        await show_main_menu(callback.message, context, language)


@router.callback_query(F.data.startswith("menu:"))
async def menu_callback(callback: CallbackQuery, context: AppContext) -> None:
    if callback.message is None or not isinstance(callback.message, Message):
        return
    is_admin = await context.admins.is_admin(callback.from_user.id)
    language = context.languages.get(callback.from_user.id, "ru") if is_admin else "ru"
    action = (callback.data or "").partition(":")[2]
    await callback.answer()
    context.menu_messages[callback.from_user.id] = (
        callback.message.chat.id,
        callback.message.message_id,
    )
    if action == "home":
        await show_main_menu(callback.message, context, language)
    elif action == "recolor":
        await context.ui.edit(
            callback.message,
            text(
                language,
                "send_source",
                icon=context.premium.html("UPLOAD"),
                **context.premium.placeholders(),
            ),
            reply_markup=menu_back_keyboard(context.premium, language),
        )
    elif action == "packs":
        if not is_admin:
            await show_main_menu(callback.message, context, "ru")
            return
        packs = await context.admins.packs(callback.from_user.id)
        if packs:
            visible = packs[-25:]
            lines = []
            for pack in reversed(visible):
                title = html.escape(pack.get("title", "Набор"))
                url = html.escape(pack.get("url", ""), quote=True)
                kind = pack.get("kind", "sticker")
                if language == "ru":
                    kind_label = (
                        "Emoji-набор" if kind == "emoji" else "Набор стикеров"
                    )
                else:
                    kind_label = (
                        "Emoji Pack" if kind == "emoji" else "Sticker Pack"
                    )
                lines.append(
                    f'{context.premium.html("PACK")} '
                    f'<a href="{url}">{title}</a> — {kind_label}'
                )
            if len(packs) > len(visible):
                lines.append(
                    f"\nПоказаны последние {len(visible)} из {len(packs)} наборов."
                    if language == "ru"
                    else f"\nShowing the latest {len(visible)} of {len(packs)} packs."
                )
            pack_list = "\n".join(lines)
        else:
            pack_list = text(
                language,
                "my_packs_empty",
                **context.premium.placeholders(),
            )
        await context.ui.edit(
            callback.message,
            text(
                language,
                "my_packs",
                icon=context.premium.html("PACK"),
                pack_list=pack_list,
                **context.premium.placeholders(),
            ),
            reply_markup=packs_keyboard(context.premium, language),
        )
    elif action == "info":
        await context.ui.edit(
            callback.message,
            text(
                language,
                "information",
                icon=context.premium.html("INFO"),
                **context.premium.placeholders(),
            ),
            reply_markup=menu_back_keyboard(context.premium, language),
        )


@router.message(Command("cancel"))
async def cancel_command(message: Message, context: AppContext) -> None:
    if message.from_user is None or message.chat.type != "private":
        return
    is_admin = await context.admins.is_admin(message.from_user.id)
    language = current_language(message, context, is_admin=is_admin)
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
