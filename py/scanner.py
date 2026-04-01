"""Filesystem scanner for ComfyUI model directories."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

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
                        "directory": directory_path.as_posix(),
                        "type": model_type,
                        "file_size": path.stat().st_size,
                    }
                )

    LOGGER.info("Discovered %s local model files", len(models))
    return models
