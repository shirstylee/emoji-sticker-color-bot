"""Privacy-preserving SQLite repository."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import aiosqlite

ALLOWED_TABLES = frozenset({"admins", "app_settings", "aggregate_statistics"})


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._connection: aiosqlite.Connection | None = None
        self._admin_settings_lock = asyncio.Lock()

    async def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self.path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA foreign_keys=ON")
        await self._connection.execute("PRAGMA busy_timeout=5000")
        await self._migrate()

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("Database is not open")
        return self._connection

    async def _migrate(self) -> None:
        await self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS admins (
                telegram_user_id INTEGER PRIMARY KEY,
                role TEXT NOT NULL CHECK(role IN ('owner', 'admin')),
                added_at TEXT NOT NULL,
                added_by INTEGER NULL,
                is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
                language TEXT NOT NULL DEFAULT 'ru',
                created_packs_json TEXT NOT NULL DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS aggregate_statistics (
                date TEXT PRIMARY KEY,
                jobs_total INTEGER NOT NULL DEFAULT 0,
                jobs_success INTEGER NOT NULL DEFAULT 0,
                jobs_failed INTEGER NOT NULL DEFAULT 0,
                items_processed INTEGER NOT NULL DEFAULT 0,
                tgs_processed INTEGER NOT NULL DEFAULT 0,
                webm_processed INTEGER NOT NULL DEFAULT 0,
                raster_processed INTEGER NOT NULL DEFAULT 0,
                emoji_packs_created INTEGER NOT NULL DEFAULT 0,
                sticker_packs_created INTEGER NOT NULL DEFAULT 0,
                telegram_429 INTEGER NOT NULL DEFAULT 0,
                processing_ms_total INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        await self._ensure_columns(
            "admins",
            {
                "language": "TEXT NOT NULL DEFAULT 'ru'",
                "created_packs_json": "TEXT NOT NULL DEFAULT '[]'",
            },
        )
        await self._ensure_columns(
            "aggregate_statistics",
            {
                "jobs_total": "INTEGER NOT NULL DEFAULT 0",
                "jobs_success": "INTEGER NOT NULL DEFAULT 0",
                "jobs_failed": "INTEGER NOT NULL DEFAULT 0",
                "items_processed": "INTEGER NOT NULL DEFAULT 0",
                "tgs_processed": "INTEGER NOT NULL DEFAULT 0",
                "webm_processed": "INTEGER NOT NULL DEFAULT 0",
                "raster_processed": "INTEGER NOT NULL DEFAULT 0",
                "emoji_packs_created": "INTEGER NOT NULL DEFAULT 0",
                "sticker_packs_created": "INTEGER NOT NULL DEFAULT 0",
                "telegram_429": "INTEGER NOT NULL DEFAULT 0",
                "processing_ms_total": "INTEGER NOT NULL DEFAULT 0",
            },
        )
        await self.connection.commit()

    async def _ensure_columns(self, table: str, columns: Mapping[str, str]) -> None:
        cursor = await self.connection.execute(f"PRAGMA table_info({table})")
        existing = {str(row["name"]) for row in await cursor.fetchall()}
        for name, declaration in columns.items():
            if name not in existing:
                await self.connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN {name} {declaration}"
                )

    async def ensure_owner(self, owner_id: int) -> None:
        now = datetime.now(UTC).isoformat()
        await self.connection.execute(
            """
            INSERT INTO admins(telegram_user_id, role, added_at, added_by, is_active)
            VALUES (?, 'owner', ?, NULL, 1)
            ON CONFLICT(telegram_user_id) DO UPDATE SET role='owner', is_active=1
            """,
            (owner_id, now),
        )
        await self.connection.commit()

    async def admin_role(self, telegram_user_id: int) -> str | None:
        cursor = await self.connection.execute(
            "SELECT role FROM admins WHERE telegram_user_id=? AND is_active=1",
            (telegram_user_id,),
        )
        row = await cursor.fetchone()
        return str(row["role"]) if row else None

    async def is_admin(self, telegram_user_id: int) -> bool:
        return await self.admin_role(telegram_user_id) is not None

    async def list_admins(self) -> list[tuple[int, str]]:
        cursor = await self.connection.execute(
            "SELECT telegram_user_id, role FROM admins WHERE is_active=1 ORDER BY role DESC, added_at"
        )
        rows = await cursor.fetchall()
        return [(int(row["telegram_user_id"]), str(row["role"])) for row in rows]

    async def add_admin(self, telegram_user_id: int, added_by: int) -> None:
        if telegram_user_id <= 0:
            raise ValueError("Telegram user ID must be positive")
        now = datetime.now(UTC).isoformat()
        await self.connection.execute(
            """
            INSERT INTO admins(telegram_user_id, role, added_at, added_by, is_active)
            VALUES (?, 'admin', ?, ?, 1)
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                role=CASE WHEN admins.role='owner' THEN 'owner' ELSE 'admin' END,
                is_active=1
            """,
            (telegram_user_id, now, added_by),
        )
        await self.connection.commit()

    async def remove_admin(self, telegram_user_id: int) -> bool:
        cursor = await self.connection.execute(
            "DELETE FROM admins WHERE telegram_user_id=? AND role='admin'",
            (telegram_user_id,),
        )
        await self.connection.commit()
        return cursor.rowcount > 0

    async def admin_language(self, telegram_user_id: int) -> str:
        cursor = await self.connection.execute(
            "SELECT language FROM admins WHERE telegram_user_id=? AND is_active=1",
            (telegram_user_id,),
        )
        row = await cursor.fetchone()
        language = str(row["language"]) if row else "ru"
        return language if language in {"ru", "en"} else "ru"

    async def set_admin_language(self, telegram_user_id: int, language: str) -> None:
        if language not in {"ru", "en"}:
            raise ValueError("Unsupported administrator language")
        await self.connection.execute(
            "UPDATE admins SET language=? WHERE telegram_user_id=? AND is_active=1",
            (language, telegram_user_id),
        )
        await self.connection.commit()

    async def admin_packs(self, telegram_user_id: int) -> list[dict[str, str]]:
        cursor = await self.connection.execute(
            "SELECT created_packs_json FROM admins WHERE telegram_user_id=? AND is_active=1",
            (telegram_user_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return []
        try:
            payload = json.loads(str(row["created_packs_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        if not isinstance(payload, list):
            return []
        result: list[dict[str, str]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            clean = {
                key: str(item[key])
                for key in ("title", "url", "kind", "created_at")
                if key in item
            }
            if clean.get("title") and clean.get("url"):
                result.append(clean)
        return result

    async def add_admin_packs(
        self, telegram_user_id: int, packs: Sequence[Mapping[str, str]]
    ) -> None:
        if not packs:
            return
        async with self._admin_settings_lock:
            existing = await self.admin_packs(telegram_user_id)
            for pack in packs:
                clean = {
                    key: str(pack[key])
                    for key in ("title", "url", "kind", "created_at")
                    if key in pack
                }
                if clean.get("title") and clean.get("url"):
                    existing.append(clean)
            await self.connection.execute(
                "UPDATE admins SET created_packs_json=? "
                "WHERE telegram_user_id=? AND is_active=1",
                (json.dumps(existing, ensure_ascii=False), telegram_user_id),
            )
            await self.connection.commit()

    async def get_setting(self, key: str, default: Any = None) -> Any:
        cursor = await self.connection.execute("SELECT value FROM app_settings WHERE key=?", (key,))
        row = await cursor.fetchone()
        return json.loads(str(row["value"])) if row else default

    async def set_setting(self, key: str, value: Any) -> None:
        await self.connection.execute(
            """
            INSERT INTO app_settings(key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, json.dumps(value, ensure_ascii=False), datetime.now(UTC).isoformat()),
        )
        await self.connection.commit()

    async def increment_statistics(self, values: Mapping[str, int], day: date | None = None) -> None:
        allowed = {
            "jobs_total",
            "jobs_success",
            "jobs_failed",
            "items_processed",
            "tgs_processed",
            "webm_processed",
            "raster_processed",
            "emoji_packs_created",
            "sticker_packs_created",
            "telegram_429",
            "processing_ms_total",
        }
        clean = {key: int(value) for key, value in values.items() if key in allowed and value}
        if not clean:
            return
        current_day = (day or datetime.now(UTC).date()).isoformat()
        await self.connection.execute(
            "INSERT INTO aggregate_statistics(date) VALUES (?) ON CONFLICT(date) DO NOTHING",
            (current_day,),
        )
        assignments = ", ".join(f"{key}={key}+?" for key in clean)
        await self.connection.execute(
            f"UPDATE aggregate_statistics SET {assignments} WHERE date=?",
            (*clean.values(), current_day),
        )
        await self.connection.commit()

    async def today_statistics(self) -> dict[str, int]:
        current_day = datetime.now(UTC).date().isoformat()
        cursor = await self.connection.execute(
            "SELECT * FROM aggregate_statistics WHERE date=?", (current_day,)
        )
        row = await cursor.fetchone()
        if row is None:
            return {}
        result: dict[str, int] = {}
        for key in row.keys():  # noqa: SIM118 - aiosqlite.Row iterates values, not keys
            if key != "date":
                result[key] = int(row[key])
        return result

    async def table_names(self) -> set[str]:
        cursor = await self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        return {str(row["name"]) for row in await cursor.fetchall()}

    async def assert_privacy_schema(self) -> None:
        unexpected = await self.table_names() - ALLOWED_TABLES
        if unexpected:
            raise RuntimeError(f"Unexpected persistent tables: {sorted(unexpected)}")

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        await self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield self.connection
        except BaseException:
            await self.connection.rollback()
            raise
        else:
            await self.connection.commit()
