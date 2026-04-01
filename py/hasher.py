"""Hashing helpers with optional Blake3 support."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

LOGGER = logging.getLogger(__name__)

try:
    import blake3 as _blake3  # type: ignore

    HAS_BLAKE3 = True
except ImportError:
    _blake3 = None
    HAS_BLAKE3 = False

CHUNK_SIZE = 8 * 1024 * 1024
_BLAKE3_AUTO_THREADS = getattr(_blake3, "AUTO", None) if _blake3 is not None else None


def hash_file(path: Path) -> dict[str, str | None]:
    """Calculate the preferred hash for a file, falling back to SHA256 when needed."""
    LOGGER.debug("Hashing file %s", path)
    result: dict[str, str | None] = {"sha256": None, "blake3": None}

    if HAS_BLAKE3 and _blake3 is not None:
        try:
            if _BLAKE3_AUTO_THREADS is not None:
                blake_hasher = _blake3.blake3(max_threads=_BLAKE3_AUTO_THREADS)
            else:
                blake_hasher = _blake3.blake3()
            blake_hasher.update_mmap(str(path))
            result["blake3"] = blake_hasher.hexdigest()
            LOGGER.debug("Computed Blake3 hash for %s", path)
            return result
        except OSError:
            LOGGER.exception("Failed to compute Blake3 hash for %s; falling back to SHA256", path)

    if HAS_BLAKE3:
        LOGGER.debug("Blake3 unavailable for %s result; using SHA256 fallback", path)

    sha256 = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            sha256.update(chunk)
    result["sha256"] = sha256.hexdigest()
    LOGGER.debug("Computed SHA256 hash for %s", path)
    return result


def preferred_hash(hashes: dict[str, str | None]) -> tuple[str, str]:
    """Return the preferred hash for CivitAI lookup."""
    if hashes.get("blake3"):
        return "blake3", str(hashes["blake3"])
    return "sha256", str(hashes["sha256"])
