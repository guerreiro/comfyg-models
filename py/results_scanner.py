"""Filesystem scanner for generated ComfyUI result images."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .database import (
    compute_sha256,
    get_models_index,
    link_image_to_model,
    mark_missing_scanned_sources,
    replace_image_filter_values,
    replace_image_tags,
    upsert_image_by_sha256,
    upsert_image_source,
)
from .image_metadata import extract_comfy_metadata
from .image_indexing import build_filter_values, build_image_tags
from .settings import load_settings

LOGGER = logging.getLogger(__name__)

VALID_RESULTS_EXTENSIONS = {".png", ".webp", ".avif", ".avifs"}


@dataclass
class ResultsScanStatus:
    """In-memory status for generated images scanning."""

    status: str = "idle"
    total: int = 0
    done: int = 0
    linked: int = 0
    unresolved_models: int = 0
    current_directory: str | None = None
    current_file: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "total": self.total,
            "done": self.done,
            "linked": self.linked,
            "unresolved_models": self.unresolved_models,
        }
        if self.current_directory:
            payload["current_directory"] = self.current_directory
        if self.current_file:
            payload["current_file"] = self.current_file
        if self.error:
            payload["error"] = self.error
        return payload


RESULTS_SCAN_STATUS = ResultsScanStatus()
_RESULTS_SCAN_TASK: asyncio.Task[None] | None = None


async def _normalize_scan_paths() -> list[Path]:
    settings = load_settings()
    raw_paths = settings.get("generated_image_scan_paths", [])
    normalized: list[Path] = []
    for raw_path in raw_paths:
        try:
            path = Path(str(raw_path)).expanduser()
        except Exception:
            LOGGER.warning("Skipping invalid results scan path value %r", raw_path)
            continue
        if not path.is_absolute():
            LOGGER.warning("Skipping non-absolute results scan path %s", path)
            continue
        normalized.append(path)
    return normalized


async def _discover_result_images() -> list[Path]:
    scan_roots = await _normalize_scan_paths()
    discovered: list[Path] = []
    for root in scan_roots:
        if not root.exists():
            LOGGER.warning("Results scan root does not exist: %s", root)
            continue
        LOGGER.info("Scanning generated images in %s", root)
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in VALID_RESULTS_EXTENSIONS:
                if not path.name.startswith("._") and path.name != ".DS_Store":
                    discovered.append(path)
    LOGGER.info("Discovered %s generated result images", len(discovered))
    return discovered


def _build_models_index(models: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, str], dict[str, str | None]]:
    by_id: dict[str, str] = {}
    by_filename: dict[str, str] = {}
    stem_candidates: dict[str, set[str]] = {}
    for model in models:
        model_id = str(model["id"])
        filename = str(model["filename"])
        by_id[model_id] = model_id
        by_filename[filename] = model_id
        stem = Path(filename).stem
        stem_candidates.setdefault(stem, set()).add(model_id)
    by_stem: dict[str, str | None] = {}
    for stem, ids in stem_candidates.items():
        by_stem[stem] = next(iter(ids)) if len(ids) == 1 else None
    return by_id, by_filename, by_stem


def _resolve_model_refs(model_refs: list[str], models: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    by_id, by_filename, by_stem = _build_models_index(models)
    matched: list[str] = []
    unresolved: list[str] = []
    for ref in model_refs:
        normalized = ref.strip()
        if not normalized:
            continue
        if normalized in by_id:
            matched.append(by_id[normalized])
            continue
        if normalized in by_filename:
            matched.append(by_filename[normalized])
            continue
        stem_match = by_stem.get(Path(normalized).stem)
        if stem_match:
            matched.append(stem_match)
        else:
            unresolved.append(normalized)
    return sorted(set(matched)), sorted(set(unresolved))


async def start_results_scan_job() -> bool:
    """Start a generated images scan job if one is not already running."""
    global _RESULTS_SCAN_TASK
    if _RESULTS_SCAN_TASK is not None and not _RESULTS_SCAN_TASK.done():
        LOGGER.info("Results scan request ignored because another job is already running")
        return False

    RESULTS_SCAN_STATUS.status = "scanning"
    RESULTS_SCAN_STATUS.total = 0
    RESULTS_SCAN_STATUS.done = 0
    RESULTS_SCAN_STATUS.linked = 0
    RESULTS_SCAN_STATUS.unresolved_models = 0
    RESULTS_SCAN_STATUS.current_directory = None
    RESULTS_SCAN_STATUS.current_file = None
    RESULTS_SCAN_STATUS.error = None

    loop = asyncio.get_running_loop()
    _RESULTS_SCAN_TASK = loop.create_task(_run_results_scan_job())
    LOGGER.info("Started background results scan job")
    return True


async def _run_results_scan_job() -> None:
    try:
        files = await _discover_result_images()
        RESULTS_SCAN_STATUS.total = len(files)
        local_models = await get_models_index()
        scan_roots = await _normalize_scan_paths()
        seen_paths_by_root: dict[str, set[str]] = {root.as_posix(): set() for root in scan_roots}

        for index, file_path in enumerate(files, start=1):
            RESULTS_SCAN_STATUS.current_directory = file_path.parent.as_posix()
            RESULTS_SCAN_STATUS.current_file = file_path.as_posix()
            LOGGER.info("Processing generated image %s (%s/%s)", file_path, index, len(files))

            sha256 = await asyncio.to_thread(compute_sha256, file_path)
            metadata = await asyncio.to_thread(extract_comfy_metadata, file_path)
            image_id = await upsert_image_by_sha256(
                sha256,
                width=metadata.get("width"),
                height=metadata.get("height"),
                format_name=metadata.get("format"),
                has_comfy_metadata=bool(metadata.get("has_comfy_metadata")),
                prompt_text=metadata.get("prompt_text"),
            )

            scan_root = next((root for root in scan_roots if root in file_path.parents or root == file_path.parent), file_path.parent)
            seen_paths_by_root.setdefault(scan_root.as_posix(), set()).add(file_path.as_posix())

            await upsert_image_source(
                image_id,
                source_type="scanned_file",
                storage_type="external",
                path=file_path.as_posix(),
                filename=file_path.name,
                scan_root=scan_root.as_posix(),
                is_present=True,
            )

            matched_models, unresolved_models = _resolve_model_refs(
                list(metadata.get("model_refs", [])) + list(metadata.get("lora_refs", [])),
                local_models,
            )
            for model_id in matched_models:
                await link_image_to_model(model_id, image_id, "workflow")
            RESULTS_SCAN_STATUS.linked += len(matched_models)
            RESULTS_SCAN_STATUS.unresolved_models += len(unresolved_models)

            tags = build_image_tags(
                source_type="scanned",
                metadata=metadata,
                unresolved_models=unresolved_models,
                scan_root=scan_root,
                file_path=file_path,
            )
            await replace_image_tags(image_id, tags)
            await replace_image_filter_values(image_id, build_filter_values(metadata))
            RESULTS_SCAN_STATUS.done = index

        for scan_root, seen_paths in seen_paths_by_root.items():
            await mark_missing_scanned_sources(scan_root, seen_paths)

        RESULTS_SCAN_STATUS.status = "idle"
        RESULTS_SCAN_STATUS.current_directory = None
        RESULTS_SCAN_STATUS.current_file = None
        LOGGER.info("Background results scan finished successfully")
    except Exception as exc:
        LOGGER.exception("Background results scan failed")
        RESULTS_SCAN_STATUS.status = "idle"
        RESULTS_SCAN_STATUS.error = str(exc)
        RESULTS_SCAN_STATUS.current_directory = None
        RESULTS_SCAN_STATUS.current_file = None


def get_results_scan_status() -> dict[str, Any]:
    """Return the current generated images scan status."""
    return RESULTS_SCAN_STATUS.to_dict()

async def stop_results_scan_job() -> bool:
    """Stop any running results scan job."""
    global _RESULTS_SCAN_TASK
    if _RESULTS_SCAN_TASK is not None and not _RESULTS_SCAN_TASK.done():
        _RESULTS_SCAN_TASK.cancel()
        RESULTS_SCAN_STATUS.status = "idle"
        LOGGER.info("Results scan job cancelled by user")
        return True
    return False
