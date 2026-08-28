from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite
import pytest

from app.database.admins import AdminService
from app.database.connection import ALLOWED_TABLES, Database
from app.logging import configure_logging


@pytest.mark.asyncio
async def test_database_contains_only_allowed_tables_and_owner(tmp_path: Path) -> None:
    database = Database(tmp_path / "bot.db")
    await database.open()
    await database.ensure_owner(111111)
    assert await database.table_names() == ALLOWED_TABLES
    assert await database.admin_role(111111) == "owner"
    await database.assert_privacy_schema()
    await database.close()


@pytest.mark.asyncio
async def test_admin_management_cannot_remove_owner(tmp_path: Path) -> None:
    database = Database(tmp_path / "bot.db")
    await database.open()
    await database.ensure_owner(100001)
    service = AdminService(database, 100001)
    await service.add(100001, 100002)
    assert await database.admin_role(100002) == "admin"
    assert not await service.remove(100001, 100001)
    assert await service.remove(100001, 100002)
    assert await database.admin_role(100001) == "owner"
    await database.close()


@pytest.mark.asyncio
async def test_admin_language_and_created_packs_survive_restart(tmp_path: Path) -> None:
    path = tmp_path / "bot.db"
    database = Database(path)
    await database.open()
    await database.ensure_owner(100001)
    await database.set_admin_language(100001, "en")
    await database.add_admin_packs(
        100001,
        [
            {
                "title": "Blue Emoji",
                "url": "https://t.me/addemoji/blue_by_bot",
                "kind": "emoji",
                "created_at": "2026-08-29T00:00:00+00:00",
            }
        ],
    )
    await database.increment_statistics({"jobs_total": 1, "jobs_success": 1})
    assert (await database.today_statistics())["jobs_total"] == 1
    await database.close()

    reopened = Database(path)
    await reopened.open()
    assert await reopened.admin_language(100001) == "en"
    packs = await reopened.admin_packs(100001)
    assert packs[0]["title"] == "Blue Emoji"
    assert packs[0]["url"] == "https://t.me/addemoji/blue_by_bot"
    await reopened.close()


@pytest.mark.asyncio
async def test_legacy_database_is_migrated_without_dashboard_index_error(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy.db"
    connection = await aiosqlite.connect(path)
    await connection.executescript(
        """
        CREATE TABLE admins (
            telegram_user_id INTEGER PRIMARY KEY,
            role TEXT NOT NULL,
            added_at TEXT NOT NULL,
            added_by INTEGER NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE aggregate_statistics (
            date TEXT PRIMARY KEY,
            total_jobs INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    await connection.commit()
    await connection.close()

    database = Database(path)
    await database.open()
    await database.ensure_owner(100001)
    await database.increment_statistics({"jobs_total": 1})

    stats = await database.today_statistics()
    assert stats["jobs_total"] == 1
    assert await database.admin_language(100001) == "ru"
    assert await database.admin_packs(100001) == []
    await database.close()


@pytest.mark.asyncio
async def test_regular_user_id_never_reaches_sqlite_or_logs(tmp_path: Path) -> None:
    regular_id = "987654321"
    database_path = tmp_path / "bot.db"
    database = Database(database_path)
    await database.open()
    await database.ensure_owner(111111)
    await database.increment_statistics({"jobs_total": 1, "items_processed": 2})
    await database.close()
    configure_logging(tmp_path / "logs")
    logging.getLogger("privacy-test").info("ordinary user %s processed", regular_id)
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert regular_id.encode() not in database_path.read_bytes()
    assert regular_id not in (tmp_path / "logs" / "app.log").read_text(encoding="utf-8")
