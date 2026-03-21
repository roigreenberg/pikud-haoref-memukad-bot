"""
database.py — PostgreSQL persistence layer using SQLModel + async SQLAlchemy.

The async engine is created lazily on first use (after load_dotenv() runs in
main.py), so DATABASE_URL is always resolved from the environment correctly.

DATABASE_URL must be set as an environment variable. Supabase provides a
pooled connection string starting with "postgres://" — this is normalised to
the "postgresql+psycopg://" format required by psycopg3 + SQLAlchemy.

No raw SQL strings. All queries use SQLModel's ORM select().
"""

import json
import os
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import Field, SQLModel, select

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class User(SQLModel, table=True):
    """One row per registered Telegram user."""
    chat_id: int = Field(primary_key=True)
    locations: str = Field(default="[]")  # JSON-encoded list[str]


# ---------------------------------------------------------------------------
# Engine (lazy singleton — created after load_dotenv() in main.py)
# ---------------------------------------------------------------------------

_engine = None
_session_factory: Optional[async_sessionmaker] = None


def _get_session_factory() -> async_sessionmaker:
    global _engine, _session_factory
    if _session_factory is None:
        raw_url: str = os.environ["DATABASE_URL"]

        # Normalise legacy "postgres://" and plain "postgresql://" to the
        # psycopg3 + SQLAlchemy driver scheme.
        if raw_url.startswith("postgres://"):
            raw_url = raw_url.replace("postgres://", "postgresql+psycopg://", 1)
        elif raw_url.startswith("postgresql://") and "+psycopg" not in raw_url:
            raw_url = raw_url.replace("postgresql://", "postgresql+psycopg://", 1)

        _engine = create_async_engine(raw_url, echo=False, pool_pre_ping=True)
        _session_factory = async_sessionmaker(
            _engine, expire_on_commit=False, class_=AsyncSession
        )
    return _session_factory


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Create tables if they don't exist (runs on startup)."""
    _get_session_factory()  # ensure _engine is initialised
    async with _engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(SQLModel.metadata.create_all)


async def is_registered(chat_id: int) -> bool:
    """Return True if the user has a row in the database."""
    async with _get_session_factory()() as session:
        user = await session.get(User, chat_id)
        return user is not None


async def register_user(chat_id: int) -> None:
    """Insert a new user row (no-op if already registered)."""
    async with _get_session_factory()() as session:
        existing = await session.get(User, chat_id)
        if existing is None:
            session.add(User(chat_id=chat_id, locations="[]"))
            await session.commit()


async def set_locations(chat_id: int, locations: list[str]) -> None:
    """Persist a JSON-encoded list of locations for the given user."""
    async with _get_session_factory()() as session:
        user = await session.get(User, chat_id)
        if user is not None:
            user.locations = json.dumps(locations)
            session.add(user)
            await session.commit()


async def get_locations(chat_id: int) -> list[str]:
    """Return the user's saved locations, or an empty list if none."""
    async with _get_session_factory()() as session:
        user = await session.get(User, chat_id)
        if user is None:
            return []
        return json.loads(user.locations)


async def get_all_users() -> list[tuple[int, list[str]]]:
    """Return all (chat_id, locations_list) pairs for broadcasting."""
    async with _get_session_factory()() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        return [(u.chat_id, json.loads(u.locations)) for u in users]
