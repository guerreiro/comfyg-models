"""SQLite helpers and schema bootstrap for comfyg-models."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
import json
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


async def upsert_models(models: list[dict[str, Any]]) -> None:
    """Insert or update scanned models without overwriting enriched metadata."""
    if not models:
        LOGGER.debug("No scanned models to persist")
        return

    rows = [
        (
            model["id"],
            model["filename"],
            model["directory"],
            model["type"],
            model["file_size"],
        )
        for model in models
    ]

    query = """
    INSERT INTO models (id, filename, directory, type, file_size)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        filename = excluded.filename,
        directory = excluded.directory,
        type = excluded.type,
        file_size = excluded.file_size
    """

    LOGGER.info("Persisting %s scanned models into SQLite", len(rows))
    await executemany(query, rows)


async def list_models_missing_hashes() -> list[dict[str, Any]]:
    """Return models that still need hashing."""
    query = """
    SELECT id, filename, directory, type, file_size
    FROM models
    WHERE sha256 IS NULL
    ORDER BY created_at ASC, filename ASC
    """
    return await fetch_all(query)


async def update_model_hashes(model_id: str, sha256: str | None, blake3: str | None) -> None:
    """Persist computed hashes for a model."""
    query = """
    UPDATE models
    SET sha256 = ?,
        blake3 = ?,
        last_hash_at = CURRENT_TIMESTAMP
    WHERE id = ?
    """
    await execute(query, (sha256, blake3, model_id))


async def list_models_pending_civitai_sync() -> list[dict[str, Any]]:
    """Return models that can be looked up on CivitAI."""
    query = """
    SELECT id, filename, directory, sha256, blake3, civitai_model_id, last_civitai_sync
    FROM models
    WHERE (blake3 IS NOT NULL OR sha256 IS NOT NULL)
      AND (
        civitai_model_id IS NULL
        OR (
          civitai_model_id = -1
          AND (
            last_civitai_sync IS NULL
            OR datetime(last_civitai_sync) <= datetime('now', '-24 hours')
          )
        )
      )
    ORDER BY created_at ASC, filename ASC
    """
    return await fetch_all(query)


async def update_model_civitai_match(
    model_id: str,
    civitai_model_id: int,
    civitai_version_id: int | None,
    civitai_data: dict[str, Any] | None,
) -> None:
    """Persist a successful or negative CivitAI match result."""
    query = """
    UPDATE models
    SET civitai_model_id = ?,
        civitai_version_id = ?,
        civitai_data = ?,
        last_civitai_sync = CURRENT_TIMESTAMP
    WHERE id = ?
    """
    serialized = json.dumps(civitai_data, ensure_ascii=True) if civitai_data is not None else None
    await execute(query, (civitai_model_id, civitai_version_id, serialized, model_id))


def _build_models_where_clause(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    types = filters.get("type") or []
    if types:
        placeholders = ", ".join("?" for _ in types)
        clauses.append(f"m.type IN ({placeholders})")
        params.extend(types)

    tags = filters.get("tags") or []
    if tags:
        placeholders = ", ".join("?" for _ in tags)
        clauses.append(
            f"""
            EXISTS (
                SELECT 1 FROM model_tags tag_filter
                WHERE tag_filter.model_id = m.id
                  AND tag_filter.tag IN ({placeholders})
            )
            """
        )
        params.extend(tags)

    search = filters.get("search")
    if search:
        clauses.append("LOWER(m.filename) LIKE ?")
        params.append(f"%{str(search).lower()}%")

    base_models = filters.get("base_model") or []
    if base_models:
        base_clauses: list[str] = []
        for base_model in base_models:
            base_clauses.append("LOWER(json_extract(m.civitai_data, '$.baseModel')) = ?")
            base_clauses.append("LOWER(json_extract(m.civitai_data, '$.model.baseModel')) = ?")
            base_clauses.append("LOWER(json_extract(m.civitai_data, '$.modelVersion.baseModel')) = ?")
            params.extend([str(base_model).lower(), str(base_model).lower(), str(base_model).lower()])
        clauses.append(f"({' OR '.join(base_clauses)})")

    if not clauses:
        return "", params

    return "WHERE " + " AND ".join(clauses), params


def _models_order_by(sort: str | None, sort_dir: str | None) -> str:
    sort_key = sort or "name"
    direction = "DESC" if (sort_dir or "asc").lower() == "desc" else "ASC"
    mapping = {
        "name": "m.filename",
        "date": "m.created_at",
        "size": "m.file_size",
        "civitai_rating": "json_extract(m.civitai_data, '$.stats.rating')",
        "last_used": "m.last_used_at",
    }
    field = mapping.get(sort_key, "m.filename")
    return f"ORDER BY {field} {direction}, m.filename ASC"


def _parse_model_row(row: dict[str, Any]) -> dict[str, Any]:
    parsed = dict(row)
    civitai_data = parsed.get("civitai_data")
    tags = parsed.get("tags")
    parsed["civitai_data"] = json.loads(civitai_data) if isinstance(civitai_data, str) and civitai_data else None
    parsed["tags"] = json.loads(tags) if isinstance(tags, str) and tags else []
    return parsed


async def list_models(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return models enriched with note, tags, and rating."""
    filters = filters or {}
    where_clause, params = _build_models_where_clause(filters)
    order_clause = _models_order_by(filters.get("sort"), filters.get("sort_dir"))

    query = f"""
    SELECT
        m.id,
        m.filename,
        m.directory,
        m.type,
        m.file_size,
        m.sha256,
        m.blake3,
        m.civitai_model_id,
        m.civitai_version_id,
        m.civitai_data,
        m.last_hash_at,
        m.last_civitai_sync,
        m.last_used_at,
        m.use_count,
        m.created_at,
        (
            SELECT img.filename
            FROM model_user_images img
            WHERE img.model_id = m.id
            ORDER BY img.created_at DESC, img.id DESC
            LIMIT 1
        ) AS primary_user_image,
        note.note AS note,
        rating.rating AS rating,
        COALESCE(json_group_array(DISTINCT tags.tag) FILTER (WHERE tags.tag IS NOT NULL), '[]') AS tags
    FROM models m
    LEFT JOIN model_notes note ON note.model_id = m.id
    LEFT JOIN model_ratings rating ON rating.model_id = m.id
    LEFT JOIN model_tags tags ON tags.model_id = m.id
    {where_clause}
    GROUP BY m.id, note.note, rating.rating
    {order_clause}
    """

    rows = await fetch_all(query, params)
    return [_parse_model_row(row) for row in rows]


async def get_model_detail(model_id: str) -> dict[str, Any] | None:
    """Return a single model with related entities."""
    query = """
    SELECT
        m.id,
        m.filename,
        m.directory,
        m.type,
        m.file_size,
        m.sha256,
        m.blake3,
        m.civitai_model_id,
        m.civitai_version_id,
        m.civitai_data,
        m.last_hash_at,
        m.last_civitai_sync,
        m.last_used_at,
        m.use_count,
        m.created_at,
        (
            SELECT img.filename
            FROM model_user_images img
            WHERE img.model_id = m.id
            ORDER BY img.created_at DESC, img.id DESC
            LIMIT 1
        ) AS primary_user_image,
        note.note AS note,
        rating.rating AS rating,
        COALESCE(json_group_array(DISTINCT tags.tag) FILTER (WHERE tags.tag IS NOT NULL), '[]') AS tags
    FROM models m
    LEFT JOIN model_notes note ON note.model_id = m.id
    LEFT JOIN model_ratings rating ON rating.model_id = m.id
    LEFT JOIN model_tags tags ON tags.model_id = m.id
    WHERE m.id = ?
    GROUP BY m.id, note.note, rating.rating
    """
    row = await fetch_one(query, (model_id,))
    if row is None:
        return None

    detail = _parse_model_row(row)
    detail["user_images"] = await fetch_all(
        "SELECT id, filename, caption, prompt, negative_prompt, created_at FROM model_user_images WHERE model_id = ? ORDER BY created_at DESC",
        (model_id,),
    )
    detail["prompts"] = await fetch_all(
        "SELECT id, title, prompt, negative_prompt, notes, created_at FROM model_prompts WHERE model_id = ? ORDER BY created_at DESC",
        (model_id,),
    )
    detail["civitai_previews"] = await fetch_all(
        "SELECT url, local_filename FROM civitai_previews WHERE model_id = ? ORDER BY url ASC",
        (model_id,),
    )
    return detail


async def insert_model_user_image(
    model_id: str,
    filename: str,
    caption: str | None,
    prompt: str | None,
    negative_prompt: str | None,
) -> None:
    """Persist a user-provided image reference for a model."""
    query = """
    INSERT INTO model_user_images (model_id, filename, caption, prompt, negative_prompt)
    VALUES (?, ?, ?, ?, ?)
    """
    await execute(query, (model_id, filename, caption, prompt, negative_prompt))
