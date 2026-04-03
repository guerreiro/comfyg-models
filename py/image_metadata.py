"""PNG metadata extraction helpers for generated ComfyUI images."""

from __future__ import annotations

import json
import logging
import struct
import zlib
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _decode_png_text_chunk(chunk_type: bytes, data: bytes) -> tuple[str, str] | None:
    if chunk_type == b"tEXt":
        key, _, value = data.partition(b"\x00")
        return key.decode("utf-8", errors="ignore"), value.decode("utf-8", errors="ignore")

    if chunk_type == b"zTXt":
        key, _, remainder = data.partition(b"\x00")
        if not remainder:
            return None
        compressed = remainder[1:]
        try:
            value = zlib.decompress(compressed).decode("utf-8", errors="ignore")
        except zlib.error:
            LOGGER.warning("Failed to decode zTXt PNG metadata")
            return None
        return key.decode("utf-8", errors="ignore"), value

    if chunk_type == b"iTXt":
        parts = data.split(b"\x00", 5)
        if len(parts) < 6:
            return None
        key = parts[0].decode("utf-8", errors="ignore")
        compressed_flag = parts[1][:1]
        text_data = parts[5]
        if compressed_flag == b"\x01":
            try:
                text = zlib.decompress(text_data).decode("utf-8", errors="ignore")
            except zlib.error:
                LOGGER.warning("Failed to decode compressed iTXt PNG metadata")
                return None
        else:
            text = text_data.decode("utf-8", errors="ignore")
        return key, text

    return None


def _try_parse_json(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _extract_prompt_text(prompt_data: Any, workflow_data: Any) -> str | None:
    prompt_chunks: list[str] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                lowered = str(key).lower()
                if lowered in {"text", "prompt", "positive", "positive_prompt"} and isinstance(value, str):
                    cleaned = value.strip()
                    if cleaned and cleaned not in prompt_chunks:
                        prompt_chunks.append(cleaned)
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(prompt_data)
    visit(workflow_data)
    if prompt_chunks:
        return ", ".join(prompt_chunks)
    if isinstance(prompt_data, str) and prompt_data.strip():
        return prompt_data.strip()
    if isinstance(prompt_data, dict):
        return json.dumps(prompt_data, ensure_ascii=True)
    return None


def _extract_model_refs(prompt_data: Any, workflow_data: Any) -> tuple[list[str], list[str], list[str]]:
    model_refs: set[str] = set()
    lora_refs: set[str] = set()
    base_models: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                lowered = str(key).lower()
                if lowered in {"ckpt_name", "model", "model_name"}:
                    if isinstance(value, str) and value.strip():
                        model_refs.add(value.strip())
                if lowered in {"lora_name", "lora"}:
                    if isinstance(value, str) and value.strip():
                        lora_refs.add(value.strip())
                if lowered == "base_model" and isinstance(value, str) and value.strip():
                    base_models.add(value.strip())
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(prompt_data)
    visit(workflow_data)
    return sorted(model_refs), sorted(lora_refs), sorted(base_models)


def extract_comfy_metadata(path: Path) -> dict[str, Any]:
    """Extract ComfyUI metadata from a PNG image using only stdlib parsing."""
    result: dict[str, Any] = {
        "format": path.suffix.lower().lstrip(".") or None,
        "width": None,
        "height": None,
        "has_comfy_metadata": False,
        "prompt_text": None,
        "workflow_json": None,
        "metadata_json": {},
        "model_refs": [],
        "lora_refs": [],
        "base_model_refs": [],
    }

    if path.suffix.lower() != ".png":
        return result

    with path.open("rb") as handle:
        signature = handle.read(8)
        if signature != PNG_SIGNATURE:
            LOGGER.warning("File %s is not a valid PNG signature", path)
            return result

        while True:
            length_bytes = handle.read(4)
            if len(length_bytes) < 4:
                break
            length = struct.unpack(">I", length_bytes)[0]
            chunk_type = handle.read(4)
            chunk_data = handle.read(length)
            handle.read(4)  # crc

            if chunk_type == b"IHDR" and len(chunk_data) >= 8:
                result["width"] = struct.unpack(">I", chunk_data[0:4])[0]
                result["height"] = struct.unpack(">I", chunk_data[4:8])[0]

            decoded = _decode_png_text_chunk(chunk_type, chunk_data)
            if decoded:
                key, value = decoded
                result["metadata_json"][key] = _try_parse_json(value)

            if chunk_type == b"IEND":
                break

    metadata_json = result["metadata_json"]
    prompt_data = metadata_json.get("prompt")
    workflow_data = metadata_json.get("workflow")
    if isinstance(prompt_data, dict):
        result["has_comfy_metadata"] = True
        result["prompt_text"] = _extract_prompt_text(prompt_data, workflow_data)
    elif isinstance(prompt_data, str) and prompt_data.strip():
        result["has_comfy_metadata"] = True
        result["prompt_text"] = prompt_data

    if isinstance(workflow_data, (dict, list)):
        result["has_comfy_metadata"] = True
        result["workflow_json"] = workflow_data

    model_refs, lora_refs, base_model_refs = _extract_model_refs(prompt_data, workflow_data)
    result["model_refs"] = model_refs
    result["lora_refs"] = lora_refs
    result["base_model_refs"] = base_model_refs
    return result
