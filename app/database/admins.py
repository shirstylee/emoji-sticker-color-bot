"""Small admin-service facade kept separate from handlers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.database.connection import Database


class AdminService:
    def __init__(self, database: Database, owner_id: int) -> None:
        self.database = database
        self.owner_id = owner_id

    async def is_admin(self, user_id: int) -> bool:
        # OWNER_ID is the authoritative recovery path even if the SQLite row was
        # removed, copied from another deployment, or has not been migrated yet.
        return user_id == self.owner_id or await self.database.is_admin(user_id)

    async def is_owner(self, user_id: int) -> bool:
        return user_id == self.owner_id

    async def language(self, user_id: int) -> str:
        if not await self.is_admin(user_id):
            return "ru"
        return await self.database.admin_language(user_id)

    async def set_language(self, user_id: int, language: str) -> None:
        if not await self.is_admin(user_id):
            raise PermissionError("Only administrators can save a language")
        await self.database.set_admin_language(user_id, language)

    async def packs(self, user_id: int) -> list[dict[str, str]]:
        if not await self.is_admin(user_id):
            return []
        return await self.database.admin_packs(user_id)

    async def remember_packs(
        self, user_id: int, packs: Sequence[Mapping[str, str]]
    ) -> None:
        if not await self.is_admin(user_id):
            raise PermissionError("Only administrator packs can be persisted")
        await self.database.add_admin_packs(user_id, packs)

    async def add(self, actor_id: int, target_id: int) -> None:
        if not await self.is_owner(actor_id):
            raise PermissionError("Only the owner can add administrators")
        await self.database.add_admin(target_id, actor_id)

    async def remove(self, actor_id: int, target_id: int) -> bool:
        if not await self.is_owner(actor_id):
            raise PermissionError("Only the owner can remove administrators")
        if target_id == self.owner_id:
            return False
        return await self.database.remove_admin(target_id)
