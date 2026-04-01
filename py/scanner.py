"""Filesystem scanner for ComfyUI model directories."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .civitai import lookup_by_hash
from .database import (
    list_models_missing_hashes,
    list_models_pending_civitai_sync,
    update_model_civitai_match,
    update_model_hashes,
    upsert_models,
)
from .hasher import hash_file, preferred_hash
from .settings import load_settings

LOGGER = logging.getLogger(__name__)

MODEL_TYPES: dict[str, str] = {
    "checkpoints": "checkpoint",
    "loras": "lora",
    "vae": "vae",
    "controlnet": "controlnet",
    "embeddings": "embedding",
    "upscale_models": "upscaler",
    "clip": "clip",
    "clip_vision": "clip_vision",
}
VALID_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".bin", ".pth"}


@dataclass
class ScanStatus:
    """In-memory scan job status exposed through the API."""

    status: str = "idle"
    total: int = 0
    done: int = 0
    error: str | None = None
    current_directory: str | None = None
    hashing_total: int = 0
    hashing_done: int = 0
    current_hash_file: str | None = None
    civitai_total: int = 0
    civitai_done: int = 0
    current_civitai_model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "total": self.total,
            "done": self.done,
            "hashing_progress": {
                "total": self.hashing_total,
                "done": self.hashing_done,
            },
            "civitai_progress": {
                "total": self.civitai_total,
                "done": self.civitai_done,
            },
        }
        if self.error:
            payload["error"] = self.error
        if self.current_directory:
            payload["current_directory"] = self.current_directory
        if self.current_hash_file:
            payload["current_hash_file"] = self.current_hash_file
        if self.current_civitai_model:
            payload["current_civitai_model"] = self.current_civitai_model
        return payload


SCAN_STATUS = ScanStatus()
_SCAN_TASK: asyncio.Task[None] | None = None


def _resolve_folder_paths() -> Any | None:
    try:
        import folder_paths  # type: ignore

        return folder_paths
    except ImportError:
        LOGGER.warning("folder_paths unavailable; model scanning is disabled in this environment")
        return None


def scan_all_models() -> list[dict[str, Any]]:
    """Scan configured model directories and return discovered files."""
    folder_paths = _resolve_folder_paths()
    if folder_paths is None:
        return []

    models: list[dict[str, Any]] = []
    comfy_base = Path(folder_paths.base_path)

    for comfy_type, model_type in MODEL_TYPES.items():
        try:
            directories = folder_paths.get_folder_paths(comfy_type)
        except Exception:
            LOGGER.exception("Failed to resolve model directories for %s", comfy_type)
            continue

        for directory in directories:
            directory_path = Path(directory)
            if not directory_path.exists():
                LOGGER.debug("Skipping missing model directory %s", directory_path)
                continue

            LOGGER.info("Scanning %s for %s models", directory_path, model_type)
            for path in directory_path.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in VALID_EXTENSIONS:
                    continue

                try:
                    relative_id = path.relative_to(comfy_base).as_posix()
                except ValueError:
                    relative_id = path.as_posix()

                models.append(
                    {
                        "id": relative_id,
                        "filename": path.name,
                        "directory": path.parent.as_posix(),
                        "type": model_type,
                        "file_size": path.stat().st_size,
                    }
                )

    LOGGER.info("Discovered %s local model files", len(models))
    return models


async def start_scan_job() -> bool:
    """Start a scan job if one is not already running."""
    global _SCAN_TASK

    if _SCAN_TASK is not None and not _SCAN_TASK.done():
        LOGGER.info("Scan job request ignored because another scan is already running")
        return False

    SCAN_STATUS.status = "scanning"
    SCAN_STATUS.total = 0
    SCAN_STATUS.done = 0
    SCAN_STATUS.error = None
    SCAN_STATUS.current_directory = None
    SCAN_STATUS.hashing_total = 0
    SCAN_STATUS.hashing_done = 0
    SCAN_STATUS.current_hash_file = None
    SCAN_STATUS.civitai_total = 0
    SCAN_STATUS.civitai_done = 0
    SCAN_STATUS.current_civitai_model = None

    loop = asyncio.get_running_loop()
    _SCAN_TASK = loop.create_task(_run_scan_job())
    LOGGER.info("Started background model scan job")
    return True


async def _run_scan_job() -> None:
    """Run the model scan in the background and persist results progressively."""
    try:
        models = await asyncio.to_thread(scan_all_models)
        SCAN_STATUS.total = len(models)
        LOGGER.info("Background scan discovered %s models; persisting to database", len(models))

        for index, model in enumerate(models, start=1):
            SCAN_STATUS.current_directory = model["directory"]
            await upsert_models([model])
            SCAN_STATUS.done = index

        SCAN_STATUS.current_directory = None
        await _run_hashing_job()
        await _run_civitai_sync_job()
        SCAN_STATUS.status = "idle"
        SCAN_STATUS.current_hash_file = None
        SCAN_STATUS.current_civitai_model = None
        LOGGER.info("Background model scan finished successfully")
    except Exception as exc:
        LOGGER.exception("Background model scan failed")
        SCAN_STATUS.status = "idle"
        SCAN_STATUS.error = str(exc)
        SCAN_STATUS.current_directory = None
        SCAN_STATUS.current_hash_file = None
        SCAN_STATUS.current_civitai_model = None


async def _run_hashing_job() -> None:
    """Hash models lazily after the scan has populated the database."""
    models = await list_models_missing_hashes()
    SCAN_STATUS.hashing_total = len(models)
    SCAN_STATUS.hashing_done = 0

    if not models:
        LOGGER.info("No models require hashing after scan")
        return

    LOGGER.info("Starting lazy hashing for %s models", len(models))
    for index, model in enumerate(models, start=1):
        model_path = Path(model["directory"]) / model["filename"]
        SCAN_STATUS.current_hash_file = model_path.as_posix()
        LOGGER.info("Hashing model %s (%s/%s)", model_path, index, len(models))

        if not model_path.exists():
            LOGGER.warning("Skipping hash for missing file %s", model_path)
            SCAN_STATUS.hashing_done = index
            continue

        hashes = await asyncio.to_thread(hash_file, model_path)
        await update_model_hashes(
            model_id=str(model["id"]),
            sha256=str(hashes["sha256"]) if hashes["sha256"] else None,
            blake3=str(hashes["blake3"]) if hashes["blake3"] else None,
        )
        SCAN_STATUS.hashing_done = index
        LOGGER.info("Stored hashes for %s", model_path)

    LOGGER.info("Lazy hashing finished successfully")


async def _run_civitai_sync_job() -> None:
    """Look up hashed models on CivitAI after hashing completes."""
    models = await list_models_pending_civitai_sync()
    SCAN_STATUS.civitai_total = len(models)
    SCAN_STATUS.civitai_done = 0

    if not models:
        LOGGER.info("No models require CivitAI sync after hashing")
        return

    api_key = load_settings().get("civitai_api_key")
    LOGGER.info("Starting CivitAI sync for %s models", len(models))

    for index, model in enumerate(models, start=1):
        SCAN_STATUS.current_civitai_model = str(model["filename"])
        algorithm, hash_value = preferred_hash(
            {
                "sha256": model.get("sha256"),
                "blake3": model.get("blake3"),
            }
        )
        LOGGER.info(
            "Looking up model %s on CivitAI using %s hash (%s/%s)",
            model["filename"],
            algorithm,
            index,
            len(models),
        )

        payload = await lookup_by_hash(hash_value, algorithm, api_key=api_key)
        if payload is None:
            await update_model_civitai_match(
                model_id=str(model["id"]),
                civitai_model_id=-1,
                civitai_version_id=None,
                civitai_data=None,
            )
            LOGGER.info("No CivitAI match found for %s", model["filename"])
        else:
            await update_model_civitai_match(
                model_id=str(model["id"]),
                civitai_model_id=int(payload.get("modelId", -1)),
                civitai_version_id=int(payload["id"]) if payload.get("id") is not None else None,
                civitai_data=payload,
            )
            LOGGER.info(
                "Stored CivitAI match for %s (modelId=%s, versionId=%s)",
                model["filename"],
                payload.get("modelId"),
                payload.get("id"),
            )

        SCAN_STATUS.civitai_done = index

    LOGGER.info("CivitAI sync finished successfully")


def get_scan_status() -> dict[str, Any]:
    """Return the current scan job status."""
    return SCAN_STATUS.to_dict()
