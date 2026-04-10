"""Background worker for slow IO tasks and detached operations."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .database import (
    list_models_missing_hashes,
    list_models_pending_civitai_sync,
    update_model_civitai_match,
    update_model_hashes,
)
from .hasher import hash_file, preferred_hash
from .settings import load_settings
from .civitai import lookup_by_hash
from .database import get_model_detail

LOGGER = logging.getLogger(__name__)

WORKER_WAKE_EVENT = asyncio.Event()

class WorkerStatus:
    """Status for the background worker."""
    def __init__(self):
        self.status = "idle"
        self.error: str | None = None
        
        self.hashing_total = 0
        self.hashing_done = 0
        self.current_hash_file: str | None = None
        
        self.civitai_total = 0
        self.civitai_done = 0
        self.current_civitai_model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "error": self.error,
            "hashing_progress": {
                "total": self.hashing_total,
                "done": self.hashing_done,
            },
            "civitai_progress": {
                "total": self.civitai_total,
                "done": self.civitai_done,
            },
            "current_hash_file": self.current_hash_file,
            "current_civitai_model": self.current_civitai_model,
        }

WORKER_STATUS = WorkerStatus()
_WORKER_TASK: asyncio.Task[None] | None = None
_FILTER_TYPES: list[str] | None = None

def wake_worker(filter_types: list[str] | None = None) -> None:
    """Notify the worker that new models might be ready for hashing or syncing.
    
    Args:
        filter_types: Optional list of model types to filter (e.g., ["checkpoint", "lora"]).
                    If None, processes all types.
    """
    global _FILTER_TYPES
    _FILTER_TYPES = filter_types
    global _WORKER_TASK
    if _WORKER_TASK is None or _WORKER_TASK.done():
        start_worker()
    WORKER_WAKE_EVENT.set()

def get_worker_status() -> dict[str, Any]:
    """Return the worker progress."""
    return WORKER_STATUS.to_dict()

async def worker_loop() -> None:
    """Continuously monitor for unhashed models or pending CivitAI syncs."""
    LOGGER.info("Started background hashing worker (filter_types=%s)", _FILTER_TYPES)
    from pathlib import Path
    
    while True:
        try:
            WORKER_STATUS.status = "working"
            
            # Step 1: Hashing
            models_to_hash = await list_models_missing_hashes(_FILTER_TYPES)
            if models_to_hash:
                WORKER_STATUS.hashing_total = len(models_to_hash)
                WORKER_STATUS.hashing_done = 0
                
                for index, model in enumerate(models_to_hash, start=1):
                    model_path = Path(model["directory"]) / model["filename"]
                    WORKER_STATUS.current_hash_file = model_path.as_posix()
                    
                    if not model_path.exists():
                        WORKER_STATUS.hashing_done = index
                        continue
                        
                    hashes = await asyncio.to_thread(hash_file, model_path)
                    await update_model_hashes(
                        model_id=str(model["id"]),
                        sha256=str(hashes["sha256"]) if hashes["sha256"] else None,
                        blake3=str(hashes["blake3"]) if hashes["blake3"] else None,
                    )
                    WORKER_STATUS.hashing_done = index
            else:
                WORKER_STATUS.hashing_total = 0
                WORKER_STATUS.hashing_done = 0
                WORKER_STATUS.current_hash_file = None

            # Step 2: CivitAI Sync
            models_to_sync = await list_models_pending_civitai_sync(_FILTER_TYPES)
            if models_to_sync:
                WORKER_STATUS.civitai_total = len(models_to_sync)
                WORKER_STATUS.civitai_done = 0
                api_key = load_settings().get("civitai_api_key")
                
                for index, model in enumerate(models_to_sync, start=1):
                    WORKER_STATUS.current_civitai_model = str(model["filename"])
                    algorithm, hash_value = preferred_hash(
                        {
                            "sha256": model.get("sha256"),
                            "blake3": model.get("blake3"),
                        }
                    )
                    payload = await lookup_by_hash(hash_value, algorithm, api_key=api_key)
                    
                    if payload is None:
                        await update_model_civitai_match(
                            model_id=str(model["id"]),
                            civitai_model_id=-1,
                            civitai_version_id=None,
                            civitai_data=None,
                        )
                    else:
                        version_id = payload.get("id")
                        await update_model_civitai_match(
                            model_id=str(model["id"]),
                            civitai_model_id=int(payload.get("modelId", -1)),
                            civitai_version_id=int(version_id) if version_id is not None else None,
                            civitai_data=payload,
                        )
                    WORKER_STATUS.civitai_done = index
            else:
                WORKER_STATUS.civitai_total = 0
                WORKER_STATUS.civitai_done = 0
                WORKER_STATUS.current_civitai_model = None
                
            WORKER_STATUS.status = "idle"
            # Wait for manual wake trigger or a scheduled 1-hour interval
            WORKER_WAKE_EVENT.clear()
            try:
                await asyncio.wait_for(WORKER_WAKE_EVENT.wait(), timeout=3600)
            except asyncio.TimeoutError:
                pass # Normal hour timeout

        except Exception as exc:
            LOGGER.exception("Background worker encountered an error")
            WORKER_STATUS.status = "error"
            WORKER_STATUS.error = str(exc)
            await asyncio.sleep(60) # Wait a minute before retrying

def start_worker() -> None:
    LOGGER.info("Registering background hashing worker onto event loop")
    try:
        loop = asyncio.get_running_loop()
        global _WORKER_TASK
        _WORKER_TASK = loop.create_task(worker_loop())
    except RuntimeError:
        # If there's no loop running yet (like during import), rely on caller to start it later
        pass

async def stop_worker() -> bool:
    """Stop the background worker if it is doing something (hashing/syncing)."""
    global _WORKER_TASK
    if WORKER_STATUS.status != "idle":
        # We don't want to kill the whole loop permanently, just current iteration
        WORKER_STATUS.status = "idle"
        WORKER_STATUS.hashing_total = 0
        WORKER_STATUS.hashing_done = 0
        WORKER_STATUS.civitai_total = 0
        WORKER_STATUS.civitai_done = 0
        
        if _WORKER_TASK and not _WORKER_TASK.done():
             _WORKER_TASK.cancel()
             # The loop will restart itself if we are in the main ComfyUI process
             # but we need to ensure it's re-created.
             return True
    return False

async def sync_single_model(model_id: str) -> bool:
    """Manually hash and sync a single model with CivitAI."""
    from pathlib import Path
    
    model = await get_model_detail(model_id)
    if not model or not model.get("filename") or not model.get("directory"):
        return False
        
    model_path = Path(model["directory"]) / model["filename"]
    if not model_path.exists():
        return False
        
    hashes = await asyncio.to_thread(hash_file, model_path)
    await update_model_hashes(
        model_id=model_id,
        sha256=str(hashes["sha256"]) if hashes["sha256"] else None,
        blake3=str(hashes["blake3"]) if hashes["blake3"] else None,
    )
    
    api_key = load_settings().get("civitai_api_key")
    algorithm, hash_value = preferred_hash(
        {
            "sha256": hashes.get("sha256"),
            "blake3": hashes.get("blake3"),
        }
    )
    if hash_value:
        payload = await lookup_by_hash(hash_value, algorithm, api_key=api_key)
        if payload is None:
            await update_model_civitai_match(
                model_id=model_id,
                civitai_model_id=-1,
                civitai_version_id=None,
                civitai_data=None,
            )
        else:
            version_id = payload.get("id")
            await update_model_civitai_match(
                model_id=model_id,
                civitai_model_id=int(payload.get("modelId", -1)),
                civitai_version_id=int(version_id) if version_id is not None else None,
                civitai_data=payload,
            )
            
    return True

