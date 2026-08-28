from __future__ import annotations

import logging
from pathlib import Path

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

