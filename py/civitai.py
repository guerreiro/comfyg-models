"""CivitAI client helpers with safe logging and simple rate limiting hooks."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib import error, parse, request

LOGGER = logging.getLogger(__name__)

API_BASE_URL = "https://civitai.com/api/v1"
REQUEST_TIMEOUT_SECONDS = 20
REQUEST_SEMAPHORE = asyncio.Semaphore(4)


class CivitaiHttpError(Exception):
    """Structured CivitAI HTTP error with optional response details."""

    def __init__(self, status: int, message: str, body: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.body = body


async def _request_json(
    path: str,
    api_key: str | None = None,
    params: dict[str, Any] | None = None,
    *,
    use_query_token: bool = False,
) -> dict[str, Any]:
    """Perform a CivitAI API request without leaking secrets in logs."""
    query_params = dict(params or {})
    if api_key and use_query_token:
        query_params["token"] = api_key

    url = f"{API_BASE_URL}/{path.lstrip('/')}"
    if query_params:
        url = f"{url}?{parse.urlencode(query_params, doseq=True)}"

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "comfyg-models/0.1",
    }
    if api_key and not use_query_token:
        headers["Authorization"] = f"Bearer {api_key}"

    LOGGER.debug(
        "Issuing CivitAI request to %s using %s authentication",
        path,
        "query-token" if use_query_token else "header",
    )

    async with REQUEST_SEMAPHORE:
        return await asyncio.to_thread(_request_json_sync, url, headers)


def _request_json_sync(url: str, headers: dict[str, str]) -> dict[str, Any]:
    req = request.Request(url, headers=headers)
    try:
        with request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except error.HTTPError as exc:
        body_text: str | None = None
        try:
            body_text = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body_text = None

        raise CivitaiHttpError(
            status=exc.code,
            message=f"CivitAI returned HTTP {exc.code}",
            body=body_text,
        ) from exc


async def _request_json_with_fallback(
    path: str,
    api_key: str,
    params: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    """Try header auth first and fall back to the query-token mode."""
    header_error: CivitaiHttpError | None = None

    try:
        return await _request_json(path, api_key=api_key, params=params), "header"
    except CivitaiHttpError as exc:
        header_error = exc
        if exc.status not in {401, 403}:
            raise
        LOGGER.warning(
            "CivitAI request to %s failed with %s using header auth. Response body: %s",
            path,
            exc.status,
            (exc.body or "<empty>")[:300],
        )

    try:
        return await _request_json(path, api_key=api_key, params=params, use_query_token=True), "query-token"
    except CivitaiHttpError as exc:
        LOGGER.warning(
            "CivitAI request to %s failed with %s using query-token auth. Response body: %s",
            path,
            exc.status,
            (exc.body or "<empty>")[:300],
        )
        if header_error is not None and exc.status in {401, 403}:
            raise header_error
        raise


async def verify_api_key(api_key: str) -> tuple[bool, str | None, str | None]:
    """Verify a CivitAI API key using the /me endpoint."""
    try:
        payload, auth_mode = await _request_json_with_fallback("/me", api_key=api_key)
    except CivitaiHttpError as exc:
        LOGGER.warning(
            "CivitAI API key verification failed with status %s. Response body: %s",
            exc.status,
            (exc.body or "<empty>")[:300],
        )
        if exc.status in {401, 403}:
            try:
                await _request_json_with_fallback(
                    "/models",
                    api_key=api_key,
                    params={"hidden": "true", "limit": 1},
                )
            except CivitaiHttpError:
                return False, None, "Invalid API key"

            LOGGER.info("CivitAI key accepted by an authenticated endpoint, but /me did not return profile data")
            return True, None, None

        return False, None, f"CivitAI returned HTTP {exc.status}"
    except Exception:
        LOGGER.exception("Unexpected failure while verifying CivitAI API key")
        return False, None, "Failed to verify API key"

    username = payload.get("username")
    if not isinstance(username, str) or not username:
        LOGGER.warning("CivitAI /me response did not include a username")
        return True, None, None

    LOGGER.info("Verified CivitAI API key successfully for user %s using %s auth", username, auth_mode)
    return True, username, None


async def lookup_by_hash(hash_value: str, algorithm: str, api_key: str | None = None) -> dict[str, Any] | None:
    """Look up a model version by hash."""
    LOGGER.debug("Looking up CivitAI model by %s hash", algorithm)
    try:
        payload = await _request_json(f"/model-versions/by-hash/{hash_value}", api_key=api_key)
    except CivitaiHttpError as exc:
        if exc.status == 404:
            LOGGER.info("CivitAI lookup returned 404 for %s hash", algorithm)
            return None
        LOGGER.warning("CivitAI hash lookup failed with status %s", exc.status)
        raise
    return payload
