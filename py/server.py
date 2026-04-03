"""HTTP route registration and settings API handlers for comfyg-models."""

from __future__ import annotations

import json
import logging
import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

from .database import (
    compute_sha256,
    delete_model_user_image,
    delete_managed_image_source,
    get_image_detail,
    get_image_filter_buckets,
    get_model_detail,
    link_image_to_model,
    list_images,
    list_models,
    replace_image_filter_values,
    replace_image_tags,
    set_primary_model_user_image,
    set_primary_model_gallery_image,
    upsert_image_by_sha256,
    upsert_image_source,
)
from .civitai import verify_api_key
from .image_metadata import extract_comfy_metadata
from .image_indexing import build_filter_values, build_image_tags
from .results_scanner import get_results_scan_status, start_results_scan_job
from .scanner import get_scan_status, start_scan_job
from .settings import ensure_data_dir, load_settings, redact_settings, save_settings

LOGGER = logging.getLogger(__name__)

try:
    from aiohttp import ClientSession, web  # type: ignore

    HAS_AIOHTTP = True
except ImportError:
    ClientSession = None  # type: ignore[assignment]
    web = None  # type: ignore[assignment]
    HAS_AIOHTTP = False


class ApiError(Exception):
    """Structured API error used for consistent JSON responses."""

    def __init__(self, message: str, code: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


def error_payload(message: str, code: str) -> dict[str, str]:
    """Return a standardized API error payload."""
    return {"error": message, "code": code}


async def build_settings_response_payload() -> dict[str, Any]:
    """Return settings in the frontend-safe shape."""
    settings = load_settings()
    payload = redact_settings(settings)
    LOGGER.debug("Prepared redacted settings payload with keys: %s", ", ".join(sorted(payload.keys())))
    return payload


async def update_settings_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate, persist, and optionally verify settings."""
    existing_settings = load_settings()
    next_settings = dict(existing_settings)

    if "preview_cache_enabled" in payload:
        next_settings["preview_cache_enabled"] = bool(payload["preview_cache_enabled"])
    if "show_nsfw_previews" in payload:
        next_settings["show_nsfw_previews"] = bool(payload["show_nsfw_previews"])
    if "generated_image_scan_paths" in payload:
        raw_paths = payload["generated_image_scan_paths"]
        if not isinstance(raw_paths, list):
            raise ApiError("generated_image_scan_paths must be a list", "INVALID_SCAN_PATHS", 400)
        normalized_paths: list[str] = []
        for raw_path in raw_paths:
            path = Path(str(raw_path)).expanduser()
            if not path.is_absolute():
                LOGGER.warning("Ignoring non-absolute generated image scan path %s", path)
                continue
            normalized_paths.append(path.as_posix())
        next_settings["generated_image_scan_paths"] = list(dict.fromkeys(normalized_paths))

    civitai_username: str | None = None
    incoming_key = payload.get("civitai_api_key")
    if incoming_key is not None:
        normalized_key = str(incoming_key).strip()
        if normalized_key:
            is_valid, username, error = await verify_api_key(normalized_key)
            if not is_valid:
                raise ApiError(error or "Invalid API key", "INVALID_CIVITAI_API_KEY", 400)
            civitai_username = username
            next_settings["civitai_api_key"] = normalized_key
        else:
            next_settings.pop("civitai_api_key", None)

    save_settings(next_settings)
    response = {
        "ok": True,
        "settings": redact_settings(next_settings),
    }
    if civitai_username:
        response["civitai_username"] = civitai_username

    LOGGER.info("Settings updated successfully")
    return response


def _json_response(payload: dict[str, Any], status: int = 200) -> Any:
    if not HAS_AIOHTTP or web is None:
        return payload
    return web.json_response(payload, status=status)


def register_routes(routes: Any) -> None:
    """Register API routes on the ComfyUI route table."""
    if not HAS_AIOHTTP:
        LOGGER.warning("aiohttp is not installed; API routes were not registered")
        return

    routes.get("/comfyg-models/api/settings")(get_settings_handler)
    routes.put("/comfyg-models/api/settings")(put_settings_handler)
    routes.post("/comfyg-models/api/scan")(post_scan_handler)
    routes.get("/comfyg-models/api/scan/status")(get_scan_status_handler)
    routes.post("/comfyg-models/api/results/scan")(post_results_scan_handler)
    routes.get("/comfyg-models/api/results/scan/status")(get_results_scan_status_handler)
    routes.get("/comfyg-models/api/fs/directories")(get_directories_handler)
    routes.post("/comfyg-models/api/fs/pick-directory")(post_pick_directory_handler)
    routes.get("/comfyg-models/api/civitai/{path:.*}")(civitai_proxy_handler)
    routes.get("/comfyg-models/api/models")(get_models_handler)
    routes.get(r"/comfyg-models/api/models/{model_id:.+}")(get_model_detail_handler)
    routes.get(r"/comfyg-models/api/images/{image_id:\d+}")(get_image_detail_handler)
    routes.get(r"/comfyg-models/api/images/{image_id:\d+}/content")(get_image_content_handler)
    routes.post(r"/comfyg-models/api/images/{image_id:\d+}/reveal")(post_image_reveal_handler)
    routes.get("/comfyg-models/api/images/filters")(get_image_filters_handler)
    routes.get("/comfyg-models/api/images")(get_images_handler)
    routes.post("/comfyg-models/api/images")(post_image_ingest_handler)
    routes.post(r"/comfyg-models/api/models/{model_id:.+}/images")(post_model_image_handler)
    routes.put(r"/comfyg-models/api/models/{model_id:.+}/images/{image_id:\d+}/primary")(put_model_primary_image_handler)
    routes.delete(r"/comfyg-models/api/models/{model_id:.+}/images/{image_id:\d+}")(delete_model_image_handler)
    routes.get("/comfyg-models/api/user-images/{filename}")(get_user_image_handler)
    LOGGER.info("Registered settings API routes")


async def get_settings_handler(_request: Any) -> Any:
    """Handle GET /comfyg-models/api/settings."""
    payload = await build_settings_response_payload()
    return _json_response(payload)


async def put_settings_handler(request: Any) -> Any:
    """Handle PUT /comfyg-models/api/settings."""
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        LOGGER.warning("Received invalid JSON payload in PUT /settings")
        return _json_response(error_payload("Invalid JSON payload", "INVALID_JSON"), status=400)
    except Exception:
        LOGGER.exception("Failed to parse PUT /settings payload")
        return _json_response(error_payload("Failed to parse request body", "REQUEST_PARSE_ERROR"), status=400)

    if not isinstance(payload, dict):
        LOGGER.warning("PUT /settings received a non-object payload")
        return _json_response(error_payload("Payload must be a JSON object", "INVALID_PAYLOAD"), status=400)

    try:
        result = await update_settings_payload(payload)
    except ApiError as exc:
        LOGGER.warning("Settings update rejected with code %s", exc.code)
        return _json_response(error_payload(exc.message, exc.code), status=exc.status)
    except Exception:
        LOGGER.exception("Unexpected failure while updating settings")
        return _json_response(error_payload("Internal server error", "INTERNAL_ERROR"), status=500)

    return _json_response(result)


async def post_scan_handler(_request: Any) -> Any:
    """Handle POST /comfyg-models/api/scan."""
    try:
        started = await start_scan_job()
    except Exception:
        LOGGER.exception("Unexpected failure while starting a scan job")
        return _json_response(error_payload("Failed to start scan", "SCAN_START_ERROR"), status=500)

    if not started:
        return _json_response({"status": "already_running"})

    return _json_response({"status": "started"})


async def get_scan_status_handler(_request: Any) -> Any:
    """Handle GET /comfyg-models/api/scan/status."""
    return _json_response(get_scan_status())


async def post_results_scan_handler(_request: Any) -> Any:
    """Handle POST /comfyg-models/api/results/scan."""
    try:
        started = await start_results_scan_job()
    except Exception:
        LOGGER.exception("Unexpected failure while starting a results scan job")
        return _json_response(error_payload("Failed to start results scan", "RESULTS_SCAN_START_ERROR"), status=500)
    if not started:
        return _json_response({"status": "already_running"})
    return _json_response({"status": "started"})


async def get_results_scan_status_handler(_request: Any) -> Any:
    """Handle GET /comfyg-models/api/results/scan/status."""
    return _json_response(get_results_scan_status())


def _default_directory_browser_root() -> Path:
    home = Path.home()
    if home.exists():
        return home
    return Path(os.environ.get("HOME", "/"))


async def get_directories_handler(request: Any) -> Any:
    """Handle GET /comfyg-models/api/fs/directories."""
    raw_path = request.rel_url.query.get("path")
    try:
        current_path = Path(raw_path).expanduser().resolve() if raw_path else _default_directory_browser_root().resolve()
    except Exception:
        return _json_response(error_payload("Invalid directory path", "INVALID_DIRECTORY_PATH"), status=400)

    if not current_path.exists() or not current_path.is_dir():
        return _json_response(error_payload("Directory not found", "DIRECTORY_NOT_FOUND"), status=404)

    try:
        children = sorted(
            [child for child in current_path.iterdir() if child.is_dir()],
            key=lambda item: item.name.lower(),
        )
    except PermissionError:
        return _json_response(error_payload("Permission denied for directory", "DIRECTORY_PERMISSION_DENIED"), status=403)
    except OSError:
        LOGGER.exception("Failed to browse directory %s", current_path)
        return _json_response(error_payload("Failed to browse directory", "DIRECTORY_BROWSE_ERROR"), status=500)

    return _json_response(
        {
            "path": current_path.as_posix(),
            "parent": current_path.parent.as_posix() if current_path.parent != current_path else None,
            "directories": [
                {
                    "name": child.name,
                    "path": child.as_posix(),
                }
                for child in children
            ],
        }
    )


async def post_pick_directory_handler(_request: Any) -> Any:
    """Handle POST /comfyg-models/api/fs/pick-directory using the native macOS folder picker."""
    if sys.platform != "darwin":
        return _json_response(
            error_payload("Native directory picker is only available on macOS", "DIRECTORY_PICKER_UNSUPPORTED"),
            status=501,
        )

    script = 'POSIX path of (choose folder with prompt "Select a folder to scan for generated images")'
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        LOGGER.exception("Failed to open native macOS directory picker")
        return _json_response(error_payload("Failed to open directory picker", "DIRECTORY_PICKER_ERROR"), status=500)

    if result.returncode != 0:
        stderr = (result.stderr or "").strip().lower()
        if "user canceled" in stderr or "cancelled" in stderr:
            return _json_response({"status": "cancelled"})
        LOGGER.warning("Native directory picker failed: %s", result.stderr.strip())
        return _json_response(error_payload("Failed to select directory", "DIRECTORY_PICKER_ERROR"), status=500)

    selected_path = (result.stdout or "").strip()
    if not selected_path:
        return _json_response({"status": "cancelled"})

    try:
        normalized = Path(selected_path).expanduser().resolve()
    except Exception:
        return _json_response(error_payload("Invalid selected directory", "INVALID_DIRECTORY_PATH"), status=400)

    return _json_response({"status": "selected", "path": normalized.as_posix()})


async def civitai_proxy_handler(request: Any) -> Any:
    """Handle GET /comfyg-models/api/civitai/{path:.*}."""
    if not HAS_AIOHTTP or web is None or ClientSession is None:
        return _json_response(error_payload("aiohttp is unavailable", "AIOHTTP_UNAVAILABLE"), status=500)

    path = request.match_info["path"]
    settings = load_settings()
    api_key = settings.get("civitai_api_key")
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    url = f"https://civitai.com/api/v1/{path}"
    LOGGER.debug("Proxying CivitAI request to %s", path)

    try:
        async with ClientSession() as session:
            async with session.get(url, headers=headers, params=request.rel_url.query) as response:
                payload = await response.json(content_type=None)
                return web.json_response(payload, status=response.status)
    except Exception:
        LOGGER.exception("CivitAI proxy request failed for %s", path)
        return _json_response(error_payload("Failed to reach CivitAI", "CIVITAI_PROXY_ERROR"), status=502)


def _split_query_values(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


async def get_models_handler(request: Any) -> Any:
    """Handle GET /comfyg-models/api/models."""
    filters = {
        "type": _split_query_values(request.rel_url.query.get("type")),
        "base_model": _split_query_values(request.rel_url.query.get("base_model")),
        "tags": _split_query_values(request.rel_url.query.get("tags")),
        "search": request.rel_url.query.get("search"),
        "sort": request.rel_url.query.get("sort"),
        "sort_dir": request.rel_url.query.get("sort_dir"),
    }
    try:
        items = await list_models(filters)
    except Exception:
        LOGGER.exception("Failed to list models")
        return _json_response(error_payload("Failed to load models", "MODELS_LIST_ERROR"), status=500)
    return _json_response({"items": items, "count": len(items)})


async def get_model_detail_handler(request: Any) -> Any:
    """Handle GET /comfyg-models/api/models/{model_id}."""
    model_id = request.match_info["model_id"]
    try:
        model = await get_model_detail(model_id)
    except Exception:
        LOGGER.exception("Failed to load model detail for %s", model_id)
        return _json_response(error_payload("Failed to load model detail", "MODEL_DETAIL_ERROR"), status=500)

    if model is None:
        return _json_response(error_payload("Model not found", "MODEL_NOT_FOUND"), status=404)
    return _json_response(model)


async def get_images_handler(request: Any) -> Any:
    """Handle GET /comfyg-models/api/images."""
    filters = {
        "model_id": request.rel_url.query.get("model_id"),
        "base_model": request.rel_url.query.get("base_model"),
        "model_ref": request.rel_url.query.get("model_ref"),
        "lora_ref": request.rel_url.query.get("lora_ref"),
        "source_type": request.rel_url.query.get("source_type"),
        "has_metadata": (
            None
            if request.rel_url.query.get("has_metadata") is None
            else request.rel_url.query.get("has_metadata") == "true"
        ),
        "search": request.rel_url.query.get("search"),
    }
    try:
        items = await list_images(filters)
    except Exception:
        LOGGER.exception("Failed to list canonical images")
        return _json_response(error_payload("Failed to load images", "IMAGES_LIST_ERROR"), status=500)
    return _json_response({"items": items, "count": len(items)})


async def get_image_filters_handler(request: Any) -> Any:
    """Handle GET /comfyg-models/api/images/filters."""
    filters = {
        "model_id": request.rel_url.query.get("model_id"),
        "base_model": request.rel_url.query.get("base_model"),
        "model_ref": request.rel_url.query.get("model_ref"),
        "lora_ref": request.rel_url.query.get("lora_ref"),
        "source_type": request.rel_url.query.get("source_type"),
        "has_metadata": (
            None
            if request.rel_url.query.get("has_metadata") is None
            else request.rel_url.query.get("has_metadata") == "true"
        ),
        "search": request.rel_url.query.get("search"),
    }
    try:
        buckets = await get_image_filter_buckets(filters)
    except Exception:
        LOGGER.exception("Failed to load image filter buckets")
        return _json_response(error_payload("Failed to load image filters", "IMAGE_FILTERS_ERROR"), status=500)
    return _json_response(buckets)


async def get_image_detail_handler(request: Any) -> Any:
    """Handle GET /comfyg-models/api/images/{image_id}."""
    image_id = int(request.match_info["image_id"])
    try:
        image = await get_image_detail(image_id)
    except Exception:
        LOGGER.exception("Failed to load image detail for %s", image_id)
        return _json_response(error_payload("Failed to load image detail", "IMAGE_DETAIL_ERROR"), status=500)
    if image is None:
        return _json_response(error_payload("Image not found", "IMAGE_NOT_FOUND"), status=404)
    return _json_response(image)


async def get_image_content_handler(request: Any) -> Any:
    """Handle GET /comfyg-models/api/images/{image_id}/content."""
    if not HAS_AIOHTTP or web is None:
        return _json_response(error_payload("aiohttp is unavailable", "AIOHTTP_UNAVAILABLE"), status=500)
    image_id = int(request.match_info["image_id"])
    try:
        image = await get_image_detail(image_id)
    except Exception:
        LOGGER.exception("Failed to load image content for %s", image_id)
        return _json_response(error_payload("Failed to load image", "IMAGE_CONTENT_ERROR"), status=500)
    if image is None:
        return _json_response(error_payload("Image not found", "IMAGE_NOT_FOUND"), status=404)

    for source in image.get("sources", []):
        path = source.get("path")
        if source.get("is_present") and isinstance(path, str) and Path(path).exists():
            return web.FileResponse(Path(path))

    return _json_response(error_payload("No present source found for image", "IMAGE_SOURCE_MISSING"), status=404)


async def post_image_reveal_handler(request: Any) -> Any:
    """Handle POST /comfyg-models/api/images/{image_id}/reveal."""
    image_id = int(request.match_info["image_id"])
    try:
        image = await get_image_detail(image_id)
    except Exception:
        LOGGER.exception("Failed to load image detail for reveal %s", image_id)
        return _json_response(error_payload("Failed to load image", "IMAGE_REVEAL_ERROR"), status=500)

    if image is None:
        return _json_response(error_payload("Image not found", "IMAGE_NOT_FOUND"), status=404)

    reveal_target: Path | None = None
    for source in image.get("sources", []):
        path_value = source.get("path")
        if source.get("is_present") and isinstance(path_value, str):
            candidate = Path(path_value)
            if candidate.exists():
                reveal_target = candidate.parent
                break

    if reveal_target is None:
        return _json_response(error_payload("No present source found for image", "IMAGE_SOURCE_MISSING"), status=404)

    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", reveal_target.as_posix()])
        elif sys.platform.startswith("win"):
            subprocess.Popen(["explorer", str(reveal_target)])
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", reveal_target.as_posix()])
        else:
            return _json_response(error_payload("Reveal is not supported on this platform", "REVEAL_UNSUPPORTED"), status=501)
    except Exception:
        LOGGER.exception("Failed to reveal image %s in file manager", image_id)
        return _json_response(error_payload("Failed to reveal image folder", "REVEAL_FAILED"), status=500)

    LOGGER.info("Revealed image %s in file manager at %s", image_id, reveal_target)
    return _json_response({"ok": True, "path": reveal_target.as_posix()})


def _user_images_dir() -> Path:
    directory = ensure_data_dir() / "user-images"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


async def _ingest_image_from_bytes(
    *,
    file_bytes: bytes,
    original_filename: str,
    model_id: str | None,
    caption: str | None,
    prompt: str | None,
    negative_prompt: str | None,
) -> dict[str, Any]:
    suffix = Path(original_filename).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ApiError("Unsupported image format", "INVALID_IMAGE_FORMAT", 400)

    size = len(file_bytes)
    if size == 0:
        raise ApiError("Uploaded image is empty", "EMPTY_IMAGE", 400)
    if size > 15 * 1024 * 1024:
        raise ApiError("Image exceeds 15MB limit", "IMAGE_TOO_LARGE", 400)

    temp_filename = f"{secrets.token_hex(12)}.tmp{suffix}"
    temp_path = _user_images_dir() / temp_filename
    with temp_path.open("wb") as handle:
        handle.write(file_bytes)

    try:
        metadata = extract_comfy_metadata(temp_path)
        sha256 = compute_sha256(temp_path)
        image_id = await upsert_image_by_sha256(
            str(sha256),
            width=metadata.get("width"),
            height=metadata.get("height"),
            format_name=metadata.get("format"),
            has_comfy_metadata=bool(metadata.get("has_comfy_metadata")),
            prompt_text=metadata.get("prompt_text") or prompt,
            workflow_json=metadata.get("workflow_json"),
            metadata_json=metadata.get("metadata_json"),
        )

        existing_image = await get_image_detail(image_id)
        existing_managed_source = next(
            (
                source
                for source in (existing_image or {}).get("sources", [])
                if source.get("source_type") == "upload"
                and source.get("storage_type") == "managed"
                and source.get("is_present")
            ),
            None,
        )

        if existing_managed_source and existing_managed_source.get("path"):
            target_path = Path(str(existing_managed_source["path"]))
            filename = str(existing_managed_source.get("filename") or target_path.name)
            deduplicated = True
            temp_path.unlink(missing_ok=True)
        else:
            filename = f"{secrets.token_hex(12)}{suffix}"
            target_path = _user_images_dir() / filename
            temp_path.replace(target_path)
            deduplicated = False

        await upsert_image_source(
            image_id,
            source_type="upload",
            storage_type="managed",
            path=target_path.as_posix(),
            filename=filename,
            caption=caption,
            prompt=prompt,
            negative_prompt=negative_prompt,
            is_present=True,
        )

        tags = build_image_tags(
            source_type="upload",
            metadata={
                **metadata,
                "prompt_text": metadata.get("prompt_text") or prompt,
            },
            unresolved_models=[],
            scan_root=None,
            file_path=None,
        )
        merged_tags = {
            (str(tag.get("tag")), str(tag.get("tag_type")))
            for tag in (existing_image or {}).get("tags", [])
            if tag.get("tag") and tag.get("tag_type")
        }
        merged_tags.update(tags)
        await replace_image_tags(image_id, sorted(merged_tags))
        await replace_image_filter_values(image_id, build_filter_values(metadata))

        if model_id:
            await link_image_to_model(model_id, image_id, "manual")

        LOGGER.info(
            "Ingested image %s as canonical image %s (%s bytes, deduplicated=%s)",
            original_filename,
            image_id,
            size,
            deduplicated,
        )
        return {
            "ok": True,
            "image_id": image_id,
            "filename": filename,
            "url": f"/comfyg-models/api/images/{image_id}/content",
            "deduplicated": deduplicated,
        }
    finally:
        temp_path.unlink(missing_ok=True)


async def post_model_image_handler(request: Any) -> Any:
    """Handle POST /comfyg-models/api/models/{model_id}/images."""
    if not HAS_AIOHTTP or web is None:
        return _json_response(error_payload("aiohttp is unavailable", "AIOHTTP_UNAVAILABLE"), status=500)

    model_id = request.match_info["model_id"]
    reader = await request.multipart()
    file_bytes: bytes | None = None
    original_filename: str | None = None
    caption: str | None = None
    prompt: str | None = None
    negative_prompt: str | None = None

    while True:
        field = await reader.next()
        if field is None:
            break

        if field.name == "file":
            if not field.filename:
                continue
            original_filename = field.filename
            file_bytes = await field.read(decode=False)
        elif field.name == "caption":
            caption = (await field.text()).strip() or None
        elif field.name == "prompt":
            prompt = (await field.text()).strip() or None
        elif field.name == "negative_prompt":
            negative_prompt = (await field.text()).strip() or None

    if not original_filename or file_bytes is None:
        return _json_response(error_payload("Image file is required", "IMAGE_REQUIRED"), status=400)

    try:
        result = await _ingest_image_from_bytes(
            file_bytes=file_bytes,
            original_filename=original_filename,
            model_id=model_id,
            caption=caption,
            prompt=prompt,
            negative_prompt=negative_prompt,
        )
    except ApiError as exc:
        return _json_response(error_payload(exc.message, exc.code), status=exc.status)
    except Exception:
        LOGGER.exception("Failed to ingest user image for model %s", model_id)
        return _json_response(error_payload("Failed to store image", "IMAGE_INGEST_ERROR"), status=500)

    return _json_response(result)


async def post_image_ingest_handler(request: Any) -> Any:
    """Handle POST /comfyg-models/api/images for generic Results ingestion."""
    if not HAS_AIOHTTP or web is None:
        return _json_response(error_payload("aiohttp is unavailable", "AIOHTTP_UNAVAILABLE"), status=500)

    reader = await request.multipart()
    file_bytes: bytes | None = None
    original_filename: str | None = None
    caption: str | None = None
    prompt: str | None = None
    negative_prompt: str | None = None

    while True:
        field = await reader.next()
        if field is None:
            break
        if field.name == "file":
            if not field.filename:
                continue
            original_filename = field.filename
            file_bytes = await field.read(decode=False)
        elif field.name == "caption":
            caption = (await field.text()).strip() or None
        elif field.name == "prompt":
            prompt = (await field.text()).strip() or None
        elif field.name == "negative_prompt":
            negative_prompt = (await field.text()).strip() or None

    if not original_filename or file_bytes is None:
        return _json_response(error_payload("Image file is required", "IMAGE_REQUIRED"), status=400)

    try:
        result = await _ingest_image_from_bytes(
            file_bytes=file_bytes,
            original_filename=original_filename,
            model_id=None,
            caption=caption,
            prompt=prompt,
            negative_prompt=negative_prompt,
        )
    except ApiError as exc:
        return _json_response(error_payload(exc.message, exc.code), status=exc.status)
    except Exception:
        LOGGER.exception("Failed to ingest generic image into Results")
        return _json_response(error_payload("Failed to store image", "IMAGE_INGEST_ERROR"), status=500)

    return _json_response(result)


async def get_user_image_handler(request: Any) -> Any:
    """Handle GET /comfyg-models/api/user-images/{filename}."""
    if not HAS_AIOHTTP or web is None:
        return _json_response(error_payload("aiohttp is unavailable", "AIOHTTP_UNAVAILABLE"), status=500)

    filename = Path(request.match_info["filename"]).name
    image_path = _user_images_dir() / filename
    if not image_path.exists():
        return _json_response(error_payload("Image not found", "IMAGE_NOT_FOUND"), status=404)
    return web.FileResponse(image_path)


async def put_model_primary_image_handler(request: Any) -> Any:
    """Handle PUT /comfyg-models/api/models/{model_id}/images/{image_id}/primary."""
    model_id = request.match_info["model_id"]
    image_id = int(request.match_info["image_id"])
    try:
        await set_primary_model_gallery_image(model_id, image_id)
        model = await get_model_detail(model_id)
        if model and not any(int(image.get("id", -1)) == image_id for image in model.get("gallery_images", [])):
            await set_primary_model_user_image(model_id, image_id)
    except Exception:
        LOGGER.exception("Failed to set primary user image for model %s", model_id)
        return _json_response(error_payload("Failed to set primary image", "PRIMARY_IMAGE_ERROR"), status=500)
    return _json_response({"ok": True})


async def delete_model_image_handler(request: Any) -> Any:
    """Handle DELETE /comfyg-models/api/models/{model_id}/images/{image_id}."""
    model_id = request.match_info["model_id"]
    image_id = int(request.match_info["image_id"])
    try:
        image = await delete_managed_image_source(model_id, image_id)
        if image is None:
            image = await delete_model_user_image(model_id, image_id)
    except Exception:
        LOGGER.exception("Failed to delete user image %s for model %s", image_id, model_id)
        return _json_response(error_payload("Failed to delete image", "DELETE_IMAGE_ERROR"), status=500)

    if image is None:
        return _json_response(error_payload("Image not found", "IMAGE_NOT_FOUND"), status=404)

    image_path = _user_images_dir() / Path(str(image["filename"])).name
    if str(image.get("storage_type")) == "managed" and image_path.exists():
        image_path.unlink()

    LOGGER.info("Deleted user image %s for model %s", image_id, model_id)
    return _json_response({"ok": True})
