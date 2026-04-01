"""HTTP route registration and settings API handlers for comfyg-models."""

from __future__ import annotations

import json
import logging
import secrets
from pathlib import Path
from typing import Any, Mapping

from .database import get_model_detail, insert_model_user_image, list_models
from .civitai import verify_api_key
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
    routes.get("/comfyg-models/api/civitai/{path:.*}")(civitai_proxy_handler)
    routes.get("/comfyg-models/api/models")(get_models_handler)
    routes.get(r"/comfyg-models/api/models/{model_id:.+}")(get_model_detail_handler)
    routes.post(r"/comfyg-models/api/models/{model_id:.+}/images")(post_model_image_handler)
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


def _user_images_dir() -> Path:
    directory = ensure_data_dir() / "user-images"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


async def post_model_image_handler(request: Any) -> Any:
    """Handle POST /comfyg-models/api/models/{model_id}/images."""
    if not HAS_AIOHTTP or web is None:
        return _json_response(error_payload("aiohttp is unavailable", "AIOHTTP_UNAVAILABLE"), status=500)

    model_id = request.match_info["model_id"]
    reader = await request.multipart()
    uploaded_file = None
    caption: str | None = None
    prompt: str | None = None
    negative_prompt: str | None = None

    while True:
        field = await reader.next()
        if field is None:
            break

        if field.name == "file":
            uploaded_file = field
        elif field.name == "caption":
            caption = (await field.text()).strip() or None
        elif field.name == "prompt":
            prompt = (await field.text()).strip() or None
        elif field.name == "negative_prompt":
            negative_prompt = (await field.text()).strip() or None

    if uploaded_file is None or not uploaded_file.filename:
        return _json_response(error_payload("Image file is required", "IMAGE_REQUIRED"), status=400)

    suffix = Path(uploaded_file.filename).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        return _json_response(error_payload("Unsupported image format", "INVALID_IMAGE_FORMAT"), status=400)

    safe_filename = f"{secrets.token_hex(12)}{suffix}"
    target_path = _user_images_dir() / safe_filename

    size = 0
    with target_path.open("wb") as handle:
        while True:
            chunk = await uploaded_file.read_chunk()
            if not chunk:
                break
            size += len(chunk)
            if size > 15 * 1024 * 1024:
                target_path.unlink(missing_ok=True)
                return _json_response(error_payload("Image exceeds 15MB limit", "IMAGE_TOO_LARGE"), status=400)
            handle.write(chunk)

    await insert_model_user_image(model_id, safe_filename, caption, prompt, negative_prompt)
    LOGGER.info("Stored user image %s for model %s", safe_filename, model_id)
    return _json_response(
        {
            "ok": True,
            "filename": safe_filename,
            "url": f"/comfyg-models/api/user-images/{safe_filename}",
        }
    )


async def get_user_image_handler(request: Any) -> Any:
    """Handle GET /comfyg-models/api/user-images/{filename}."""
    if not HAS_AIOHTTP or web is None:
        return _json_response(error_payload("aiohttp is unavailable", "AIOHTTP_UNAVAILABLE"), status=500)

    filename = Path(request.match_info["filename"]).name
    image_path = _user_images_dir() / filename
    if not image_path.exists():
        return _json_response(error_payload("Image not found", "IMAGE_NOT_FOUND"), status=404)
    return web.FileResponse(image_path)
