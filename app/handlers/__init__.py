"""Aiogram routers."""

from aiogram import Dispatcher

from app.handlers import admin, commands, workflow


def register_handlers(dispatcher: Dispatcher) -> None:
    dispatcher.include_router(admin.router)
    dispatcher.include_router(commands.router)
    dispatcher.include_router(workflow.router)
