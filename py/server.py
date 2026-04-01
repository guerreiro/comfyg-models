"""HTTP route registration and settings API handlers for comfyg-models."""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from .civitai import verify_api_key
from .settings import load_settings, redact_settings, save_settings

LOGGER = logging.getLogger(__name__)

try:
    from aiohttp import web  # type: ignore

    HAS_AIOHTTP = True
except ImportError:
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
