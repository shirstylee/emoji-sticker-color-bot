"""Non-personal mutable application settings."""

from __future__ import annotations

from dataclasses import fields

from app.database.connection import Database
from app.models.limits import LimitsConfig


async def load_limits(database: Database) -> LimitsConfig:
    defaults = LimitsConfig()
    values: dict[str, int] = {}
    for item in fields(defaults):
        current = await database.get_setting(f"limit.{item.name}", getattr(defaults, item.name))
        values[item.name] = max(1, int(current))
    return LimitsConfig(**values)


async def maintenance_enabled(database: Database) -> bool:
    return bool(await database.get_setting("maintenance_enabled", False))

