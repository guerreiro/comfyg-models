"""SQLite helpers and schema bootstrap for comfyg-models."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Iterable, Sequence

import aiosqlite

from .settings import ensure_data_dir, get_data_dir

LOGGER = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DB_FILENAME = "cache.db"

SCHEMA_STATEMENTS = """
CREATE TABLE IF NOT EXISTS models (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    directory TEXT NOT NULL,
    type TEXT NOT NULL,
    file_size INTEGER,
    sha256 TEXT,
    blake3 TEXT,
    civitai_model_id INTEGER,
    civitai_version_id INTEGER,
    civitai_data JSON,
    last_hash_at TIMESTAMP,
    last_civitai_sync TIMESTAMP,
    last_used_at TIMESTAMP,
    use_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS model_notes (
    model_id TEXT PRIMARY KEY REFERENCES models(id) ON DELETE CASCADE,
    note TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS model_tags (
    model_id TEXT REFERENCES models(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (model_id, tag)
);

CREATE TABLE IF NOT EXISTS model_ratings (
    model_id TEXT PRIMARY KEY REFERENCES models(id) ON DELETE CASCADE,
    rating INTEGER CHECK (rating BETWEEN 1 AND 5)
);

CREATE TABLE IF NOT EXISTS model_user_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT REFERENCES models(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    caption TEXT,
    prompt TEXT,
    negative_prompt TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS model_prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT REFERENCES models(id) ON DELETE CASCADE,
    title TEXT,
    prompt TEXT NOT NULL,
    negative_prompt TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS civitai_previews (
    model_id TEXT REFERENCES models(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    local_filename TEXT,
    PRIMARY KEY (model_id, url)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value JSON
);

CREATE INDEX IF NOT EXISTS idx_models_type ON models(type);
CREATE INDEX IF NOT EXISTS idx_models_civitai ON models(civitai_model_id);
CREATE INDEX IF NOT EXISTS idx_model_tags_tag ON model_tags(tag);
"""


def get_db_path() -> Path:
    """Return the SQLite database path."""
    return get_data_dir() / DB_FILENAME


async def get_connection() -> aiosqlite.Connection:
    """Create a reusable aiosqlite connection with the expected pragmas."""
    connection = await aiosqlite.connect(get_db_path())
    connection.row_factory = aiosqlite.Row
    await connection.execute("PRAGMA foreign_keys = ON")
    return connection


@asynccontextmanager
async def connection_context() -> AsyncIterator[aiosqlite.Connection]:
    """Yield a configured aiosqlite connection and close it safely."""
    connection = await get_connection()
    try:
        yield connection
    finally:
        await connection.close()


async def init_db() -> None:
    """Initialize the SQLite database and apply migrations."""
    ensure_data_dir()
    db_path = get_db_path()
    LOGGER.info("Initializing SQLite database at %s", db_path)

    async with connection_context() as connection:
        async with connection.execute("PRAGMA user_version") as cursor:
            row = await cursor.fetchone()
        user_version = int(row[0] if row is not None else 0)
        LOGGER.debug("Current database schema version is %s", user_version)

        if user_version > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema version {user_version} is newer than supported version {SCHEMA_VERSION}"
            )

        if user_version < 1:
            LOGGER.info("Applying schema version 1")
            await connection.executescript(SCHEMA_STATEMENTS)
            await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        else:
            await connection.executescript(SCHEMA_STATEMENTS)

        await connection.commit()
        LOGGER.info("Database initialization finished with schema version %s", SCHEMA_VERSION)


async def execute(query: str, params: Sequence[Any] | None = None) -> None:
    """Execute a write query asynchronously."""
    async with connection_context() as connection:
        await connection.execute(query, params or ())
        await connection.commit()


async def fetch_one(query: str, params: Sequence[Any] | None = None) -> dict[str, Any] | None:
    """Fetch a single row as a dictionary."""
    async with connection_context() as connection:
        async with connection.execute(query, params or ()) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row is not None else None


async def fetch_all(query: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
    """Fetch all rows as dictionaries."""
    async with connection_context() as connection:
        async with connection.execute(query, params or ()) as cursor:
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def executemany(query: str, rows: Iterable[Sequence[Any]]) -> None:
    """Execute a batch write operation asynchronously."""
    async with connection_context() as connection:
        await connection.executemany(query, list(rows))
        await connection.commit()
