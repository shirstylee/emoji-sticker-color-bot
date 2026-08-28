"""SQLite access limited to admins, application settings, and aggregate statistics."""

from app.database.connection import Database

__all__ = ["Database"]

