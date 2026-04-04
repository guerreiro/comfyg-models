"""ComfyUI entry point for the comfyg-models plugin."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Awaitable

from .py.database import init_db
from .py.worker import worker_loop
from .py.server import register_routes
from .py.settings import ensure_data_dir, get_data_dir

LOGGER = logging.getLogger(__name__)

WEB_DIRECTORY = "web/dist"
NODE_CLASS_MAPPINGS: dict[str, Any] = {}
NODE_DISPLAY_NAME_MAPPINGS: dict[str, str] = {}
PLUGIN_ROOT = Path(__file__).resolve().parent
WEB_DIST = PLUGIN_ROOT / "web" / "dist"
DATA_DIR = get_data_dir()


def _run_async_task(coro: Awaitable[Any]) -> None:
    """Run async startup work in the current loop when available."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        LOGGER.debug("No running loop detected during import; using asyncio.run for startup work")
        asyncio.run(coro)
        return

    LOGGER.debug("Scheduling startup coroutine on existing event loop")
    loop.create_task(coro)


def _register_static_routes() -> None:
    """Register SPA routes when ComfyUI and aiohttp are available."""
    try:
        from aiohttp import web
        from server import PromptServer
    except ImportError:
        LOGGER.warning("ComfyUI server dependencies unavailable; static routes were not registered")
        return

    routes = PromptServer.instance.routes

    @routes.get("/comfyg-models")
    async def serve_spa(_request: Any) -> Any:
        LOGGER.debug("Serving comfyg-models SPA from %s", WEB_DIST / "index.html")
        return web.FileResponse(WEB_DIST / "index.html")

    @routes.get("/comfyg-models/assets/{filename}")
    async def serve_assets(request: Any) -> Any:
        filename = request.match_info["filename"]
        asset_path = WEB_DIST / "assets" / filename
        LOGGER.debug("Serving static asset %s", asset_path)
        return web.FileResponse(asset_path)

    register_routes(routes)
    LOGGER.info("Registered comfyg-models static and API routes")


def _startup() -> None:
    """Prepare runtime directories and database during plugin import."""
    ensure_data_dir()
    LOGGER.info("Runtime data directory ready at %s", DATA_DIR)
    _register_static_routes()
    _run_async_task(init_db())


_startup()
