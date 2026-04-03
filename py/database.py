"""SQLite helpers and schema bootstrap for comfyg-models."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path
from typing import Any, AsyncIterator, Iterable, Sequence

import aiosqlite

from .settings import ensure_data_dir, get_data_dir

LOGGER = logging.getLogger(__name__)

SCHEMA_VERSION = 4
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
    is_primary INTEGER NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256 TEXT NOT NULL UNIQUE,
    width INTEGER,
    height INTEGER,
    format TEXT,
    has_comfy_metadata INTEGER NOT NULL DEFAULT 0,
    prompt_text TEXT,
    workflow_json TEXT,
    metadata_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS image_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    storage_type TEXT NOT NULL,
    path TEXT,
    filename TEXT NOT NULL,
    caption TEXT,
    prompt TEXT,
    negative_prompt TEXT,
    scan_root TEXT,
    is_present INTEGER NOT NULL DEFAULT 1,
    last_seen_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS model_image_links (
    model_id TEXT NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (model_id, image_id, relation_type)
);

CREATE TABLE IF NOT EXISTS image_tags (
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    tag_type TEXT NOT NULL,
    PRIMARY KEY (image_id, tag, tag_type)
);

CREATE TABLE IF NOT EXISTS image_filter_values (
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    filter_type TEXT NOT NULL,
    filter_value TEXT NOT NULL,
    PRIMARY KEY (image_id, filter_type, filter_value)
);

CREATE INDEX IF NOT EXISTS idx_models_type ON models(type);
CREATE INDEX IF NOT EXISTS idx_models_civitai ON models(civitai_model_id);
CREATE INDEX IF NOT EXISTS idx_model_tags_tag ON model_tags(tag);
CREATE INDEX IF NOT EXISTS idx_images_sha256 ON images(sha256);
CREATE INDEX IF NOT EXISTS idx_image_sources_image ON image_sources(image_id);
CREATE INDEX IF NOT EXISTS idx_image_sources_type ON image_sources(source_type);
CREATE INDEX IF NOT EXISTS idx_image_sources_present ON image_sources(is_present);
CREATE INDEX IF NOT EXISTS idx_model_image_links_model ON model_image_links(model_id);
CREATE INDEX IF NOT EXISTS idx_model_image_links_image ON model_image_links(image_id);
CREATE INDEX IF NOT EXISTS idx_image_tags_tag ON image_tags(tag);
CREATE INDEX IF NOT EXISTS idx_image_filter_values_type ON image_filter_values(filter_type);
CREATE INDEX IF NOT EXISTS idx_image_filter_values_value ON image_filter_values(filter_value);
"""

IMAGE_HASH_CHUNK_SIZE = 8 * 1024 * 1024


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
            user_version = 1
        else:
            await connection.executescript(SCHEMA_STATEMENTS)

        if user_version < 2:
            LOGGER.info("Applying schema version 2")
            columns: list[str] = []
            async with connection.execute("PRAGMA table_info(model_user_images)") as cursor:
                rows = await cursor.fetchall()
                columns = [str(row[1]) for row in rows]
            if "is_primary" not in columns:
                await connection.execute(
                    "ALTER TABLE model_user_images ADD COLUMN is_primary INTEGER NOT NULL DEFAULT 0"
                )
                await connection.execute(
                    """
                    UPDATE model_user_images
                    SET is_primary = 1
                    WHERE id IN (
                        SELECT id
                        FROM model_user_images latest
                        WHERE latest.id = (
                            SELECT inner_img.id
                            FROM model_user_images inner_img
                            WHERE inner_img.model_id = latest.model_id
                            ORDER BY inner_img.created_at DESC, inner_img.id DESC
                            LIMIT 1
                        )
                    )
                    """
                )
            user_version = 2

        if user_version < 3:
            LOGGER.info("Applying schema version 3")
            await connection.executescript(SCHEMA_STATEMENTS)
            user_version = 3

        if user_version < 4:
            LOGGER.info("Applying schema version 4")
            await connection.executescript(SCHEMA_STATEMENTS)
            user_version = 4

        await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

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


def compute_sha256(path: Path) -> str:
    """Compute a SHA256 hash for a file path."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(IMAGE_HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _parse_image_payload(row: dict[str, Any]) -> dict[str, Any]:
    parsed = dict(row)
    for key in ("workflow_json", "metadata_json", "models", "tags", "sources"):
        value = parsed.get(key)
        if isinstance(value, str) and value:
            try:
                parsed[key] = json.loads(value)
            except json.JSONDecodeError:
                LOGGER.warning("Failed to decode JSON field %s for image payload", key)
                parsed[key] = None
        elif value is None and key in {"models", "tags", "sources"}:
            parsed[key] = []

    for json_key in ("workflow_json", "metadata_json"):
        if parsed.get(json_key) is not None:
            parsed[json_key] = _sanitize_json_values(parsed[json_key])

    if parsed.get("id") is not None:
        parsed["preview_url"] = f"/comfyg-models/api/images/{parsed['id']}/content"
    return parsed


def _sanitize_json_values(obj: Any) -> Any:
    """Recursively replace non-serializable values (NaN, Inf) with null."""
    if isinstance(obj, dict):
        return {k: _sanitize_json_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_json_values(item) for item in obj]
    elif isinstance(obj, float):
        import math
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj


def _build_image_where_clause(filters: dict[str, Any], *, image_alias: str = "i") -> tuple[str, list[Any]]:
    clauses: list[str] = [
        f"EXISTS (SELECT 1 FROM image_sources srcp WHERE srcp.image_id = {image_alias}.id AND srcp.is_present = 1)"
    ]
    params: list[Any] = []

    if filters.get("model_id"):
        clauses.append(
            f"EXISTS (SELECT 1 FROM model_image_links mil WHERE mil.image_id = {image_alias}.id AND mil.model_id = ?)"
        )
        params.append(filters["model_id"])
    if filters.get("source_type"):
        clauses.append(
            f"EXISTS (SELECT 1 FROM image_sources srcf WHERE srcf.image_id = {image_alias}.id AND srcf.source_type = ? AND srcf.is_present = 1)"
        )
        params.append(filters["source_type"])
    if filters.get("has_metadata") is not None:
        clauses.append(f"{image_alias}.has_comfy_metadata = ?")
        params.append(1 if filters["has_metadata"] else 0)
    if filters.get("base_model"):
        base_model_value = filters["base_model"]
        if isinstance(base_model_value, list):
            placeholders = ", ".join("?" * len(base_model_value))
            clauses.append(
                f"EXISTS (SELECT 1 FROM image_filter_values ifv_base WHERE ifv_base.image_id = {image_alias}.id AND ifv_base.filter_type = 'base_model' AND ifv_base.filter_value IN ({placeholders}))"
            )
            params.extend(base_model_value)
        else:
            clauses.append(
                f"EXISTS (SELECT 1 FROM image_filter_values ifv_base WHERE ifv_base.image_id = {image_alias}.id AND ifv_base.filter_type = 'base_model' AND ifv_base.filter_value = ?)"
            )
            params.append(base_model_value)
    if filters.get("model_ref"):
        model_ref_value = filters["model_ref"]
        if isinstance(model_ref_value, list):
            placeholders = ", ".join("?" * len(model_ref_value))
            clauses.append(
                f"EXISTS (SELECT 1 FROM image_filter_values ifv_model WHERE ifv_model.image_id = {image_alias}.id AND ifv_model.filter_type = 'model' AND ifv_model.filter_value IN ({placeholders}))"
            )
            params.extend(model_ref_value)
        else:
            clauses.append(
                f"EXISTS (SELECT 1 FROM image_filter_values ifv_model WHERE ifv_model.image_id = {image_alias}.id AND ifv_model.filter_type = 'model' AND ifv_model.filter_value = ?)"
            )
            params.append(model_ref_value)
    if filters.get("lora_ref"):
        lora_ref_value = filters["lora_ref"]
        if isinstance(lora_ref_value, list):
            placeholders = ", ".join("?" * len(lora_ref_value))
            clauses.append(
                f"EXISTS (SELECT 1 FROM image_filter_values ifv_lora WHERE ifv_lora.image_id = {image_alias}.id AND ifv_lora.filter_type = 'lora' AND ifv_lora.filter_value IN ({placeholders}))"
            )
            params.extend(lora_ref_value)
        else:
            clauses.append(
                f"EXISTS (SELECT 1 FROM image_filter_values ifv_lora WHERE ifv_lora.image_id = {image_alias}.id AND ifv_lora.filter_type = 'lora' AND ifv_lora.filter_value = ?)"
            )
            params.append(lora_ref_value)
    if filters.get("search"):
        search_value = f"%{str(filters['search']).lower()}%"
        clauses.append(
            f"""(
                LOWER(COALESCE({image_alias}.prompt_text, '')) LIKE ?
                OR EXISTS (SELECT 1 FROM image_sources srcs WHERE srcs.image_id = {image_alias}.id AND srcs.is_present = 1 AND LOWER(srcs.filename) LIKE ?)
                OR EXISTS (SELECT 1 FROM image_tags its WHERE its.image_id = {image_alias}.id AND LOWER(its.tag) LIKE ?)
                OR EXISTS (SELECT 1 FROM image_filter_values ifvs WHERE ifvs.image_id = {image_alias}.id AND LOWER(ifvs.filter_value) LIKE ?)
            )"""
        )
        params.extend([search_value, search_value, search_value, search_value])

    return f"WHERE {' AND '.join(clauses)}", params


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
            SELECT src.filename
            FROM model_image_links mil
            JOIN image_sources src ON src.image_id = mil.image_id
            WHERE mil.model_id = m.id
              AND src.is_present = 1
              AND src.storage_type = 'managed'
            ORDER BY mil.is_primary DESC, src.created_at DESC, src.id DESC
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
            SELECT src.filename
            FROM model_image_links mil
            JOIN image_sources src ON src.image_id = mil.image_id
            WHERE mil.model_id = m.id
              AND src.is_present = 1
              AND src.storage_type = 'managed'
            ORDER BY mil.is_primary DESC, src.created_at DESC, src.id DESC
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
    detail["user_images"] = await list_model_legacy_user_images(model_id)
    detail["gallery_images"] = await list_images_for_model(model_id)
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
    existing_primary = await fetch_one(
        "SELECT id FROM model_user_images WHERE model_id = ? AND is_primary = 1 LIMIT 1",
        (model_id,),
    )
    query = """
    INSERT INTO model_user_images (model_id, filename, caption, prompt, negative_prompt, is_primary)
    VALUES (?, ?, ?, ?, ?, ?)
    """
    await execute(query, (model_id, filename, caption, prompt, negative_prompt, 0 if existing_primary else 1))


async def set_primary_model_user_image(model_id: str, image_id: int) -> None:
    """Mark one user image as the primary thumbnail for a model."""
    await execute("UPDATE model_user_images SET is_primary = 0 WHERE model_id = ?", (model_id,))
    await execute(
        "UPDATE model_user_images SET is_primary = 1 WHERE model_id = ? AND id = ?",
        (model_id, image_id),
    )


async def get_model_user_image(model_id: str, image_id: int) -> dict[str, Any] | None:
    """Return one user image row for a model."""
    return await fetch_one(
        """
        SELECT id, model_id, filename, is_primary
        FROM model_user_images
        WHERE model_id = ? AND id = ?
        """,
        (model_id, image_id),
    )


async def delete_model_user_image(model_id: str, image_id: int) -> dict[str, Any] | None:
    """Delete one user image and promote another image when needed."""
    image = await get_model_user_image(model_id, image_id)
    if image is None:
        return None

    await execute("DELETE FROM model_user_images WHERE model_id = ? AND id = ?", (model_id, image_id))

    if int(image.get("is_primary") or 0) == 1:
        replacement = await fetch_one(
            """
            SELECT id
            FROM model_user_images
            WHERE model_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (model_id,),
        )
        if replacement is not None:
            await set_primary_model_user_image(model_id, int(replacement["id"]))

    return image


async def upsert_image_by_sha256(
    sha256: str,
    *,
    width: int | None = None,
    height: int | None = None,
    format_name: str | None = None,
    has_comfy_metadata: bool = False,
    prompt_text: str | None = None,
    workflow_json: dict[str, Any] | list[Any] | None = None,
    metadata_json: dict[str, Any] | list[Any] | None = None,
) -> int:
    """Create or update a canonical image entity and return its id."""
    serialized_workflow = json.dumps(workflow_json, ensure_ascii=True) if workflow_json is not None else None
    serialized_metadata = json.dumps(metadata_json, ensure_ascii=True) if metadata_json is not None else None
    query = """
    INSERT INTO images (
        sha256, width, height, format, has_comfy_metadata, prompt_text, workflow_json, metadata_json, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(sha256) DO UPDATE SET
        width = COALESCE(excluded.width, images.width),
        height = COALESCE(excluded.height, images.height),
        format = COALESCE(excluded.format, images.format),
        has_comfy_metadata = MAX(images.has_comfy_metadata, excluded.has_comfy_metadata),
        prompt_text = COALESCE(excluded.prompt_text, images.prompt_text),
        workflow_json = COALESCE(excluded.workflow_json, images.workflow_json),
        metadata_json = COALESCE(excluded.metadata_json, images.metadata_json),
        updated_at = CURRENT_TIMESTAMP
    """
    async with connection_context() as connection:
        await connection.execute(
            query,
            (
                sha256,
                width,
                height,
                format_name,
                1 if has_comfy_metadata else 0,
                prompt_text,
                serialized_workflow,
                serialized_metadata,
            ),
        )
        async with connection.execute("SELECT id FROM images WHERE sha256 = ?", (sha256,)) as cursor:
            row = await cursor.fetchone()
        await connection.commit()
    return int(row[0])


async def upsert_image_source(
    image_id: int,
    *,
    source_type: str,
    storage_type: str,
    path: str | None,
    filename: str,
    caption: str | None = None,
    prompt: str | None = None,
    negative_prompt: str | None = None,
    scan_root: str | None = None,
    is_present: bool = True,
) -> int:
    """Create or update one physical source for a canonical image."""
    identity_path = path or ""
    query = """
    INSERT INTO image_sources (
        image_id, source_type, storage_type, path, filename, caption, prompt, negative_prompt, scan_root, is_present, last_seen_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT DO NOTHING
    """
    async with connection_context() as connection:
        existing_query = """
        SELECT id
        FROM image_sources
        WHERE image_id = ?
          AND source_type = ?
          AND storage_type = ?
          AND COALESCE(path, '') = ?
        LIMIT 1
        """
        async with connection.execute(existing_query, (image_id, source_type, storage_type, identity_path)) as cursor:
            existing = await cursor.fetchone()
        if existing is None:
            cursor = await connection.execute(
                """
                INSERT INTO image_sources (
                    image_id, source_type, storage_type, path, filename, caption, prompt, negative_prompt, scan_root, is_present, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    image_id,
                    source_type,
                    storage_type,
                    path,
                    filename,
                    caption,
                    prompt,
                    negative_prompt,
                    scan_root,
                    1 if is_present else 0,
                ),
            )
            source_id = int(cursor.lastrowid)
        else:
            source_id = int(existing[0])
            await connection.execute(
                """
                UPDATE image_sources
                SET filename = ?,
                    caption = COALESCE(?, caption),
                    prompt = COALESCE(?, prompt),
                    negative_prompt = COALESCE(?, negative_prompt),
                    scan_root = COALESCE(?, scan_root),
                    is_present = ?,
                    last_seen_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    filename,
                    caption,
                    prompt,
                    negative_prompt,
                    scan_root,
                    1 if is_present else 0,
                    source_id,
                ),
            )
        await connection.commit()
    return source_id


async def link_image_to_model(model_id: str, image_id: int, relation_type: str, *, is_primary: bool = False) -> None:
    """Create or refresh a model-image link."""
    async with connection_context() as connection:
        await connection.execute(
            """
            INSERT INTO model_image_links (model_id, image_id, relation_type, is_primary)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(model_id, image_id, relation_type) DO UPDATE SET
                is_primary = MAX(model_image_links.is_primary, excluded.is_primary)
            """,
            (model_id, image_id, relation_type, 1 if is_primary else 0),
        )
        if is_primary:
            await connection.execute(
                "UPDATE model_image_links SET is_primary = 0 WHERE model_id = ? AND image_id != ?",
                (model_id, image_id),
            )
            await connection.execute(
                "UPDATE model_image_links SET is_primary = 1 WHERE model_id = ? AND image_id = ?",
                (model_id, image_id),
            )
        await connection.commit()


async def list_model_legacy_user_images(model_id: str) -> list[dict[str, Any]]:
    """Return model gallery images using the unified tables with legacy-compatible shape."""
    query = """
    SELECT
        img.id,
        src.filename,
        src.caption,
        src.prompt,
        src.negative_prompt,
        mil.is_primary,
        src.created_at,
        src.source_type,
        src.storage_type,
        src.path,
        i.sha256,
        i.has_comfy_metadata,
        i.prompt_text
    FROM model_image_links mil
    JOIN images i ON i.id = mil.image_id
    JOIN image_sources src ON src.image_id = i.id
    JOIN images img ON img.id = i.id
    WHERE mil.model_id = ?
      AND src.is_present = 1
    GROUP BY i.id, src.id, mil.is_primary
    ORDER BY mil.is_primary DESC, src.created_at DESC, src.id DESC
    """
    rows = await fetch_all(query, (model_id,))
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append(
            {
                "id": int(row["id"]),
                "filename": row["filename"],
                "caption": row.get("caption"),
                "prompt": row.get("prompt"),
                "negative_prompt": row.get("negative_prompt"),
                "is_primary": int(row.get("is_primary") or 0),
                "created_at": row.get("created_at"),
                "source_type": row.get("source_type"),
                "storage_type": row.get("storage_type"),
                "path": row.get("path"),
                "sha256": row.get("sha256"),
                "has_comfy_metadata": int(row.get("has_comfy_metadata") or 0),
                "prompt_text": row.get("prompt_text"),
            }
        )
    if normalized:
        return normalized
    return await fetch_all(
        "SELECT id, filename, caption, prompt, negative_prompt, is_primary, created_at FROM model_user_images WHERE model_id = ? ORDER BY is_primary DESC, created_at DESC, id DESC",
        (model_id,),
    )


async def list_images_for_model(model_id: str, source_kind: str | None = None) -> list[dict[str, Any]]:
    """Return unified image entities linked to a model."""
    params: list[Any] = [model_id]
    source_clause = ""
    if source_kind == "uploaded":
        source_clause = "AND src.source_type = 'upload'"
    elif source_kind == "generated":
        source_clause = "AND src.source_type = 'scanned_file'"
    query = f"""
    SELECT
        i.id,
        i.sha256,
        i.width,
        i.height,
        i.format,
        i.has_comfy_metadata,
        i.prompt_text,
        i.workflow_json,
        i.metadata_json,
        i.created_at,
        i.updated_at,
        mil.is_primary,
        COALESCE(
            json_group_array(DISTINCT json_object(
                'id', src.id,
                'source_type', src.source_type,
                'storage_type', src.storage_type,
                'path', src.path,
                'filename', src.filename,
                'caption', src.caption,
                'prompt', src.prompt,
                'negative_prompt', src.negative_prompt,
                'scan_root', src.scan_root,
                'is_present', src.is_present,
                'created_at', src.created_at
            )) FILTER (WHERE src.id IS NOT NULL),
            '[]'
        ) AS sources,
        COALESCE(
            json_group_array(DISTINCT json_object(
                'tag', it.tag,
                'tag_type', it.tag_type
            )) FILTER (WHERE it.tag IS NOT NULL),
            '[]'
        ) AS tags
    FROM model_image_links mil
    JOIN images i ON i.id = mil.image_id
    LEFT JOIN image_sources src ON src.image_id = i.id AND src.is_present = 1 {source_clause}
    LEFT JOIN image_tags it ON it.image_id = i.id
    WHERE mil.model_id = ?
    GROUP BY i.id, mil.is_primary
    ORDER BY mil.is_primary DESC, i.created_at DESC, i.id DESC
    """
    rows = await fetch_all(query, params)
    return [_parse_image_payload(row) for row in rows]


async def list_images(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return canonical images for the Results library."""
    filters = filters or {}
    where_clause, params = _build_image_where_clause(filters)
    query = f"""
    SELECT
        i.id,
        i.sha256,
        i.width,
        i.height,
        i.format,
        i.has_comfy_metadata,
        i.prompt_text,
        i.workflow_json,
        i.metadata_json,
        i.created_at,
        i.updated_at,
        COALESCE(
            json_group_array(DISTINCT json_object(
                'id', src.id,
                'source_type', src.source_type,
                'storage_type', src.storage_type,
                'path', src.path,
                'filename', src.filename,
                'caption', src.caption,
                'prompt', src.prompt,
                'negative_prompt', src.negative_prompt,
                'scan_root', src.scan_root,
                'is_present', src.is_present,
                'created_at', src.created_at
            )) FILTER (WHERE src.id IS NOT NULL),
            '[]'
        ) AS sources,
        COALESCE(
            json_group_array(DISTINCT json_object(
                'model_id', mil.model_id,
                'relation_type', mil.relation_type,
                'is_primary', mil.is_primary,
                'filename', m.filename,
                'type', m.type
            )) FILTER (WHERE mil.model_id IS NOT NULL),
            '[]'
        ) AS models,
        COALESCE(
            json_group_array(DISTINCT json_object(
                'tag', it.tag,
                'tag_type', it.tag_type
            )) FILTER (WHERE it.tag IS NOT NULL),
            '[]'
        ) AS tags
    FROM images i
    LEFT JOIN image_sources src ON src.image_id = i.id AND src.is_present = 1
    LEFT JOIN model_image_links mil ON mil.image_id = i.id
    LEFT JOIN models m ON m.id = mil.model_id
    LEFT JOIN image_tags it ON it.image_id = i.id
    {where_clause}
    GROUP BY i.id
    ORDER BY i.updated_at DESC, i.id DESC
    """
    rows = await fetch_all(query, params)
    return [_parse_image_payload(row) for row in rows]


async def get_image_detail(image_id: int) -> dict[str, Any] | None:
    """Return one canonical image with all related data."""
    query = """
    SELECT
        i.id,
        i.sha256,
        i.width,
        i.height,
        i.format,
        i.has_comfy_metadata,
        i.prompt_text,
        i.workflow_json,
        i.metadata_json,
        i.created_at,
        i.updated_at,
        COALESCE(
            json_group_array(DISTINCT json_object(
                'id', src.id,
                'source_type', src.source_type,
                'storage_type', src.storage_type,
                'path', src.path,
                'filename', src.filename,
                'caption', src.caption,
                'prompt', src.prompt,
                'negative_prompt', src.negative_prompt,
                'scan_root', src.scan_root,
                'is_present', src.is_present,
                'created_at', src.created_at
            )) FILTER (WHERE src.id IS NOT NULL),
            '[]'
        ) AS sources,
        COALESCE(
            json_group_array(DISTINCT json_object(
                'model_id', mil.model_id,
                'relation_type', mil.relation_type,
                'is_primary', mil.is_primary,
                'filename', m.filename,
                'type', m.type
            )) FILTER (WHERE mil.model_id IS NOT NULL),
            '[]'
        ) AS models,
        COALESCE(
            json_group_array(DISTINCT json_object(
                'tag', it.tag,
                'tag_type', it.tag_type
            )) FILTER (WHERE it.tag IS NOT NULL),
            '[]'
        ) AS tags
    FROM images i
    LEFT JOIN image_sources src ON src.image_id = i.id AND src.is_present = 1
    LEFT JOIN model_image_links mil ON mil.image_id = i.id
    LEFT JOIN models m ON m.id = mil.model_id
    LEFT JOIN image_tags it ON it.image_id = i.id
    WHERE i.id = ?
    GROUP BY i.id
    """
    row = await fetch_one(query, (image_id,))
    return _parse_image_payload(row) if row is not None else None


async def replace_image_tags(image_id: int, tags: list[tuple[str, str]]) -> None:
    """Replace automatic image tags for an image."""
    async with connection_context() as connection:
        await connection.execute("DELETE FROM image_tags WHERE image_id = ?", (image_id,))
        if tags:
            await connection.executemany(
                "INSERT INTO image_tags (image_id, tag, tag_type) VALUES (?, ?, ?)",
                [(image_id, tag, tag_type) for tag, tag_type in tags],
            )
        await connection.commit()


async def replace_image_filter_values(image_id: int, filter_values: list[tuple[str, str]]) -> None:
    """Replace metadata-derived filter values for an image."""
    async with connection_context() as connection:
        await connection.execute("DELETE FROM image_filter_values WHERE image_id = ?", (image_id,))
        if filter_values:
            await connection.executemany(
                "INSERT INTO image_filter_values (image_id, filter_type, filter_value) VALUES (?, ?, ?)",
                [(image_id, filter_type, filter_value) for filter_type, filter_value in filter_values],
            )
        await connection.commit()


async def get_image_filter_buckets(filters: dict[str, Any] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Return available metadata-derived filter buckets for the Results UI."""
    filters = filters or {}
    where_clause, params = _build_image_where_clause(filters)
    query = f"""
    SELECT
        ifv.filter_type,
        ifv.filter_value,
        COUNT(DISTINCT ifv.image_id) AS count
    FROM image_filter_values ifv
    JOIN images i ON i.id = ifv.image_id
    {where_clause}
    GROUP BY ifv.filter_type, ifv.filter_value
    ORDER BY count DESC, ifv.filter_value ASC
    """
    rows = await fetch_all(query, params)
    buckets: dict[str, list[dict[str, Any]]] = {"model": [], "lora": [], "base_model": []}
    for row in rows:
        filter_type = str(row["filter_type"])
        if filter_type not in buckets:
            continue
        buckets[filter_type].append({"value": row["filter_value"], "count": int(row["count"] or 0)})
    return buckets


async def get_all_image_tags() -> list[str]:
    """Return all unique tag values from image_tags for the tag filter UI."""
    rows = await fetch_all("""
        SELECT DISTINCT tag FROM image_tags 
        WHERE tag IS NOT NULL AND tag != ''
        ORDER BY tag ASC
    """)
    return [str(row["tag"]) for row in rows]


async def mark_missing_scanned_sources(scan_root: str, seen_paths: set[str]) -> None:
    """Mark scanned file sources as missing if they were not seen in the latest scan."""
    params: list[Any] = [scan_root]
    query = """
    UPDATE image_sources
    SET is_present = 0
    WHERE source_type = 'scanned_file'
      AND scan_root = ?
    """
    if seen_paths:
        placeholders = ", ".join("?" for _ in seen_paths)
        query += f" AND path NOT IN ({placeholders})"
        params.extend(sorted(seen_paths))
    await execute(query, params)


async def get_models_index() -> list[dict[str, Any]]:
    """Return lightweight local model data for result linking."""
    return await fetch_all("SELECT id, filename, type FROM models ORDER BY filename ASC")


async def set_primary_model_gallery_image(model_id: str, image_id: int) -> None:
    """Mark one canonical image as primary for a model."""
    async with connection_context() as connection:
        await connection.execute("UPDATE model_image_links SET is_primary = 0 WHERE model_id = ?", (model_id,))
        await connection.execute(
            "UPDATE model_image_links SET is_primary = 1 WHERE model_id = ? AND image_id = ?",
            (model_id, image_id),
        )
        await connection.commit()


async def delete_managed_image_source(model_id: str, image_id: int) -> dict[str, Any] | None:
    """Delete a managed upload source for a model while preserving shared images."""
    async with connection_context() as connection:
        async with connection.execute(
            """
            SELECT src.id, src.filename, src.storage_type, src.source_type, mil.is_primary
            FROM model_image_links mil
            JOIN image_sources src ON src.image_id = mil.image_id
            WHERE mil.model_id = ?
              AND mil.image_id = ?
              AND src.source_type = 'upload'
            ORDER BY src.created_at DESC, src.id DESC
            LIMIT 1
            """,
            (model_id, image_id),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None

        source = dict(row)
        await connection.execute(
            "DELETE FROM model_image_links WHERE model_id = ? AND image_id = ? AND relation_type = 'manual'",
            (model_id, image_id),
        )
        await connection.execute("DELETE FROM image_sources WHERE id = ?", (source["id"],))

        async with connection.execute(
            "SELECT COUNT(*) FROM image_sources WHERE image_id = ?",
            (image_id,),
        ) as cursor:
            sources_left = int((await cursor.fetchone())[0])
        async with connection.execute(
            "SELECT COUNT(*) FROM model_image_links WHERE image_id = ?",
            (image_id,),
        ) as cursor:
            links_left = int((await cursor.fetchone())[0])
        if sources_left == 0 and links_left == 0:
            await connection.execute("DELETE FROM images WHERE id = ?", (image_id,))

        if int(source.get("is_primary") or 0) == 1:
            async with connection.execute(
                """
                SELECT image_id
                FROM model_image_links
                WHERE model_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (model_id,),
            ) as cursor:
                replacement = await cursor.fetchone()
            if replacement is not None:
                await connection.execute("UPDATE model_image_links SET is_primary = 0 WHERE model_id = ?", (model_id,))
                await connection.execute(
                    "UPDATE model_image_links SET is_primary = 1 WHERE model_id = ? AND image_id = ?",
                    (model_id, int(replacement[0])),
                )
        await connection.commit()
    return source


async def get_setting(key: str) -> Any | None:
    """Get a setting value from the database."""
    async with connection_context() as connection:
        async with connection.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            value = row[0]
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return value
            return value


async def set_setting(key: str, value: Any) -> None:
    """Set a setting value in the database."""
    serialized = json.dumps(value, ensure_ascii=True) if value is not None else None
    async with connection_context() as connection:
        await connection.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, serialized),
        )
        await connection.commit()
