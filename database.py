"""
database.py — Async SQLite persistence layer using aiosqlite.
"""

import json
import os

import aiosqlite

# In production (PRODUCTION=true) the DB lives on the persistent Render disk.
# Locally it's written next to the source code for convenience.
DB_PATH = "/data/bot_database.db" if os.environ.get("PRODUCTION") == "true" else "bot_database.db"


async def init_db() -> None:
    """Create the database and users table if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                locations TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        await db.commit()


async def is_registered(chat_id: int) -> bool:
    """Return True if the user already has a row in the database."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM users WHERE chat_id = ?", (chat_id,)
        ) as cursor:
            return await cursor.fetchone() is not None


async def register_user(chat_id: int) -> None:
    """Insert a new user row (no-op if already registered)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (chat_id, locations) VALUES (?, ?)",
            (chat_id, json.dumps([])),
        )
        await db.commit()


async def set_locations(chat_id: int, locations: list[str]) -> None:
    """Persist a JSON-encoded list of locations for the given user."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET locations = ? WHERE chat_id = ?",
            (json.dumps(locations), chat_id),
        )
        await db.commit()


async def get_locations(chat_id: int) -> list[str]:
    """Return the user's saved locations, or an empty list if none."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT locations FROM users WHERE chat_id = ?", (chat_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return []
            return json.loads(row[0])


async def get_all_users() -> list[tuple[int, list[str]]]:
    """Return all (chat_id, locations_list) pairs for broadcasting."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT chat_id, locations FROM users") as cursor:
            rows = await cursor.fetchall()
            return [(row[0], json.loads(row[1])) for row in rows]
