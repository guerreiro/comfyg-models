"""Settings helpers and runtime path resolution for comfyg-models."""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

LOGGER = logging.getLogger(__name__)

SETTINGS_FILENAME = "settings.json"
DEFAULT_SETTINGS: dict[str, Any] = {
    "preview_cache_enabled": True,
    "show_nsfw_previews": False,
    "generated_image_scan_paths": [],
}


@lru_cache(maxsize=1)
def get_base_path() -> Path:
    """Resolve the ComfyUI base path with a development fallback."""
    try:
        import folder_paths  # type: ignore

        base_path = Path(folder_paths.base_path)
        LOGGER.debug("Resolved ComfyUI base path from folder_paths: %s", base_path)
        return base_path
    except ImportError:
        fallback = Path(os.environ.get("COMFYUI_BASE_PATH", "/tmp/comfyg-models-dev"))
        LOGGER.warning(
            "folder_paths unavailable; using development fallback base path %s",
            fallback,
        )
        return fallback


@lru_cache(maxsize=1)
def get_data_dir() -> Path:
    """Return the runtime data directory used by the plugin."""
    return get_base_path() / "user" / "comfyg-models"


def get_settings_path() -> Path:
    """Return the path to the settings file."""
    return get_data_dir() / SETTINGS_FILENAME


def ensure_data_dir() -> Path:
    """Create the plugin runtime directory if needed."""
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    LOGGER.debug("Ensured runtime data directory exists at %s", data_dir)
    return data_dir


def load_settings() -> dict[str, Any]:
    """Load settings from disk and merge them with defaults."""
    settings_path = get_settings_path()
    ensure_data_dir()

    if not settings_path.exists():
        LOGGER.debug("Settings file missing at %s; returning defaults", settings_path)
        return dict(DEFAULT_SETTINGS)

    try:
        raw_data = json.loads(settings_path.read_text(encoding="utf-8"))
        if not isinstance(raw_data, dict):
            LOGGER.warning("Settings file %s does not contain a JSON object", settings_path)
            return dict(DEFAULT_SETTINGS)
    except (OSError, json.JSONDecodeError):
        LOGGER.exception("Failed to load settings from %s", settings_path)
        return dict(DEFAULT_SETTINGS)

    merged = dict(DEFAULT_SETTINGS)
    merged.update(raw_data)
    LOGGER.debug(
        "Loaded settings from disk with keys: %s",
        ", ".join(sorted(merged.keys())) or "<none>",
    )
    return merged


def save_settings(data: dict[str, Any]) -> Path:
    """Persist settings atomically and restrict file permissions to the owner."""
    ensure_data_dir()
    settings_path = get_settings_path()
    payload = dict(DEFAULT_SETTINGS)
    payload.update(data)

    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(settings_path.parent),
        delete=False,
    ) as temp_file:
        json.dump(payload, temp_file, ensure_ascii=True, indent=2, sort_keys=True)
        temp_file.write("\n")
        temp_path = Path(temp_file.name)

    temp_path.replace(settings_path)
    os.chmod(settings_path, 0o600)
    LOGGER.info("Saved settings to %s with restricted permissions", settings_path)
    return settings_path


def redact_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Hide secrets before returning settings to the frontend."""
    return {
        key: value
        for key, value in data.items()
        if key != "civitai_api_key"
    } | {
        "civitai_api_key_configured": bool(data.get("civitai_api_key")),
    }
