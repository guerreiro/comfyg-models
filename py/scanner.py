"""Filesystem scanner for ComfyUI model directories."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .civitai import lookup_by_hash
from .database import (
    get_existing_models_index,
    list_models_missing_hashes,
    list_models_pending_civitai_sync,
    remove_models,
    update_model_civitai_match,
    update_model_hashes,
    upsert_models,
)
from .hasher import hash_file, preferred_hash
from .settings import load_settings

BATCH_SIZE = 50


def _batch_ranges(length: int, batch_size: int) -> list[tuple[int, int]]:
    """Generate (start, end) tuples for batched iteration."""
    if length <= 0:
        return []
    return [(i, min(i + batch_size, length)) for i in range(0, length, batch_size)]

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


def scan_all_models(incremental: bool = True, existing_index: dict[str, int] | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Scan configured model directories and return discovered files.
    
    Args:
        incremental: If True, skip files already in DB with matching file_size.
        existing_index: Pre-fetched {id: file_size} dict for comparison. If None, fetched automatically.
    
    Returns:
        Tuple of (models list, list of removed model IDs that are no longer on disk).
    """
    folder_paths = _resolve_folder_paths()
    if folder_paths is None:
        return [], []

    if incremental and existing_index is None:
        existing_index = {}

    models: list[dict[str, Any]] = []
    comfy_base = Path(folder_paths.base_path)
    seen_ids: set[str] = set()

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
                
                if path.name.startswith("._") or path.name == ".DS_Store":
                    continue

                try:
                    relative_id = path.relative_to(comfy_base).as_posix()
                except ValueError:
                    relative_id = path.as_posix()

                seen_ids.add(relative_id)
                file_size = path.stat().st_size

                existing_size = existing_index.get(relative_id) if existing_index else None
                if incremental and existing_size == file_size:
                    continue

                models.append(
                    {
                        "id": relative_id,
                        "filename": path.name,
                        "directory": path.parent.as_posix(),
                        "type": model_type,
                        "file_size": file_size,
                    }
                )

    removed_ids: list[str] = []
    unchanged_count = 0
    if incremental and existing_index:
        removed_ids = [mid for mid in existing_index if mid not in seen_ids]
        unchanged_count = len(existing_index) - len(models) - len(removed_ids)

    LOGGER.info("Discovered %s local model files (%s unchanged skipped)", len(models), unchanged_count)
    return models, removed_ids


async def start_scan_job(mode: str = "quick") -> bool:
    """Start a scan job if one is not already running.
    
    Args:
        mode: "quick" (default) for incremental file scan only, "full" for scan + auto hash/sync.
    """
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
    _SCAN_TASK = loop.create_task(_run_scan_job(mode))
    LOGGER.info("Started background model scan job (mode=%s)", mode)
    return True


async def _run_scan_job(mode: str) -> None:
    """Run the model scan in the background and persist results progressively."""
    try:
        existing_index = await get_existing_models_index()
        models, removed_ids = await asyncio.to_thread(scan_all_models, True, existing_index)
        
        SCAN_STATUS.total = len(models) + len(removed_ids)
        LOGGER.info("Background scan discovered %s new/changed models, %s removed", len(models), len(removed_ids))

        for start, end in _batch_ranges(len(models), BATCH_SIZE):
            batch = models[start:end]
            if batch:
                SCAN_STATUS.current_directory = batch[0]["directory"]
            await upsert_models(batch)
            SCAN_STATUS.done = end

        if removed_ids:
            await remove_models(removed_ids)
            SCAN_STATUS.done += len(removed_ids)
            SCAN_STATUS.current_directory = None

        SCAN_STATUS.current_directory = None
        SCAN_STATUS.status = "idle"
        SCAN_STATUS.current_hash_file = None
        SCAN_STATUS.current_civitai_model = None
        LOGGER.info("Background model scan finished successfully")

        if mode == "full":
            from .worker import wake_worker
            wake_worker()
    except Exception as exc:
        LOGGER.exception("Background model scan failed")
        SCAN_STATUS.status = "idle"
        SCAN_STATUS.error = str(exc)
        SCAN_STATUS.current_directory = None
        SCAN_STATUS.current_hash_file = None
        SCAN_STATUS.current_civitai_model = None



def get_scan_status() -> dict[str, Any]:
    """Return the current scan job status combined with worker."""
    from .worker import get_worker_status, stop_worker
    worker_st = get_worker_status()
    st = SCAN_STATUS.to_dict()
    # Merge hashing/civitai progress back onto scanner status so the frontend UI doesn't break
    st["hashing_progress"] = worker_st["hashing_progress"]
    st["civitai_progress"] = worker_st["civitai_progress"]
    
    if st["status"] == "idle" and worker_st["status"] in ("working", "scanning"):
        # UI thinks it's still scanning if hashing/syncing
        st["status"] = "scanning"
    return st
async def stop_scan_job() -> bool:
    """Stop any running scan job and the worker."""
    global _SCAN_TASK
    stopped_any = False
    
    if _SCAN_TASK is not None and not _SCAN_TASK.done():
        _SCAN_TASK.cancel()
        SCAN_STATUS.status = "idle"
        LOGGER.info("Scan job cancelled by user")
        stopped_any = True
        
    from .worker import stop_worker
    worker_stopped = await stop_worker()
    if worker_stopped:
        stopped_any = True
        
    return stopped_any
