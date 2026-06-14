"""Local thumbnail cache for CivitAI preview images.

Downloads remote CivitAI image URLs and stores them as local files so the UI
can serve them from the backend instead of hitting civitai.com on every page load.
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
from pathlib import Path
from typing import Any
from urllib import request as urllib_request
from urllib.error import URLError

from .settings import get_data_dir

LOGGER = logging.getLogger(__name__)

THUMBNAIL_DIR_NAME = "thumbnail_cache"
REQUEST_TIMEOUT = 15  # seconds
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/avif", "image/gif"}
EXT_MAP = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/avif": ".avif",
    "image/gif": ".gif",
}


def get_thumbnail_dir() -> Path:
    """Return (and create) the local thumbnail cache directory."""
    cache_dir = get_data_dir() / THUMBNAIL_DIR_NAME
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _url_to_filename(url: str) -> str:
    """Derive a stable, unique local filename from a remote URL."""
    url_hash = hashlib.sha1(url.encode()).hexdigest()[:20]
    return url_hash


def get_cached_path(url: str) -> Path | None:
    """Return the local path for a cached thumbnail if it already exists."""
    cache_dir = get_thumbnail_dir()
    stem = _url_to_filename(url)
    for ext in EXT_MAP.values():
        candidate = cache_dir / f"{stem}{ext}"
        if candidate.exists():
            return candidate
    return None


def download_thumbnail(url: str) -> Path:
    """Download a remote image to the local cache and return its path.

    If it was already cached, the existing path is returned without re-downloading.

    Raises:
        ValueError: If the URL is not a valid CivitAI image URL or the content
            type is not an image.
        URLError: If the download fails.
    """
    existing = get_cached_path(url)
    if existing is not None:
        LOGGER.debug("Thumbnail already cached: %s -> %s", url, existing)
        return existing

    LOGGER.info("Downloading thumbnail: %s", url)
    req = urllib_request.Request(
        url,
        headers={
            "User-Agent": "comfyg-models/1.0 (thumbnail-cache)",
            "Accept": "image/*",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            content_type = response.headers.get_content_type() or ""
            # Normalise e.g. "image/jpeg; charset=..." -> "image/jpeg"
            content_type = content_type.split(";")[0].strip().lower()

            if content_type not in ALLOWED_CONTENT_TYPES:
                raise ValueError(
                    f"Unexpected content-type {content_type!r} when downloading thumbnail {url!r}"
                )

            ext = EXT_MAP.get(content_type, ".jpg")
            stem = _url_to_filename(url)
            cache_dir = get_thumbnail_dir()
            dest = cache_dir / f"{stem}{ext}"

            data = response.read()
    except URLError as exc:
        LOGGER.warning("Failed to download thumbnail %s: %s", url, exc)
        raise

    dest.write_bytes(data)
    LOGGER.info("Cached thumbnail %s -> %s (%d bytes)", url, dest.name, len(data))
    return dest


def get_thumbnail_mime(path: Path) -> str:
    """Return the MIME type for a cached thumbnail file."""
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "image/jpeg"


def delete_thumbnail_file(local_filename: str) -> None:
    """Delete a cached thumbnail file by its local filename. Silently ignores missing files."""
    path = get_thumbnail_dir() / local_filename
    try:
        path.unlink(missing_ok=True)
        LOGGER.info("Deleted cached thumbnail: %s", local_filename)
    except Exception as exc:
        LOGGER.warning("Failed to delete cached thumbnail %s: %s", local_filename, exc)
