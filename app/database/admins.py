"""Small admin-service facade kept separate from handlers."""

from __future__ import annotations

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
