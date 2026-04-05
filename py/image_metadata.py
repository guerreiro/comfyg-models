"""PNG/WEBP/AVIF metadata extraction helpers for generated ComfyUI images."""

from __future__ import annotations

import json
import logging
import struct
import zlib
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
WEBP_RIFF_SIGNATURE = b"RIFF"
WEBP_WEBP_SIGNATURE = b"WEBP"


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
    """Extract ComfyUI metadata from PNG, WEBP, or AVIF images."""
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

    suffix = path.suffix.lower()
    if suffix == ".png":
        return _extract_png_metadata(path, result)
    elif suffix in {".webp"}:
        return _extract_webp_metadata(path, result)
    elif suffix in {".avif", ".avifs"}:
        return _extract_avif_metadata(path, result)
    return result


def _finalize_metadata(result: dict[str, Any]) -> dict[str, Any]:
    """Extract prompt text, workflow JSON, and model refs from metadata_json."""
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


def _extract_png_metadata(path: Path, result: dict[str, Any]) -> dict[str, Any]:
    """Extract ComfyUI metadata from a PNG file."""
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

    return _finalize_metadata(result)


def _parse_exif_comfy_data(exif_bytes: bytes) -> dict[str, Any]:
    """Parse ComfyUI prompt/workflow from EXIF UserComment or ImageDescription."""
    found: dict[str, Any] = {}
    # EXIF header: 'Exif\x00\x00' then TIFF
    if not exif_bytes.startswith(b"Exif\x00\x00"):
        return found
    tiff = exif_bytes[6:]
    if len(tiff) < 8:
        return found
    byte_order = tiff[:2]
    if byte_order == b"II":
        endian = "<"
    elif byte_order == b"MM":
        endian = ">"
    else:
        return found

    magic = struct.unpack_from(f"{endian}H", tiff, 2)[0]
    if magic != 42:
        return found

    ifd_offset = struct.unpack_from(f"{endian}I", tiff, 4)[0]
    try:
        num_entries = struct.unpack_from(f"{endian}H", tiff, ifd_offset)[0]
    except struct.error:
        return found

    for i in range(num_entries):
        entry_offset = ifd_offset + 2 + i * 12
        if entry_offset + 12 > len(tiff):
            break
        tag, type_id, count = struct.unpack_from(f"{endian}HHI", tiff, entry_offset)
        raw_value = tiff[entry_offset + 8: entry_offset + 12]

        # Tag 0x010E = ImageDescription, 0x9286 = UserComment
        if tag in (0x010E, 0x9286):
            if type_id == 2:  # ASCII string
                if count > 4:
                    str_offset = struct.unpack_from(f"{endian}I", raw_value)[0]
                    raw_str = tiff[str_offset: str_offset + count].rstrip(b"\x00")
                else:
                    raw_str = raw_value[:count].rstrip(b"\x00")
                text = raw_str.decode("utf-8", errors="ignore").strip()
                if text.startswith("{") or text.startswith("["):
                    try:
                        parsed = json.loads(text)
                        # Try to detect if it's a ComfyUI prompt or workflow
                        if isinstance(parsed, dict):
                            if any(k in parsed for k in ("prompt", "workflow")):
                                found.update(parsed)
                            else:
                                found.setdefault("prompt", parsed)
                    except json.JSONDecodeError:
                        pass
    return found


def _extract_webp_metadata(path: Path, result: dict[str, Any]) -> dict[str, Any]:
    """Extract ComfyUI metadata from a WEBP file via EXIF and XMP chunks."""
    with path.open("rb") as handle:
        riff = handle.read(4)
        if riff != WEBP_RIFF_SIGNATURE:
            return result
        _file_size = handle.read(4)  # total file size
        webp = handle.read(4)
        if webp != WEBP_WEBP_SIGNATURE:
            return result

        # Read image dimensions from VP8/VP8L/VP8X chunk
        while True:
            chunk_id = handle.read(4)
            if len(chunk_id) < 4:
                break
            size_bytes = handle.read(4)
            if len(size_bytes) < 4:
                break
            chunk_size = struct.unpack("<I", size_bytes)[0]
            chunk_data = handle.read(chunk_size)
            if chunk_size % 2 == 1:
                handle.read(1)  # padding

            if chunk_id == b"VP8 " and len(chunk_data) >= 10:
                # Simple lossy: width/height encoded at bytes 6-9
                w = (struct.unpack_from("<H", chunk_data, 6)[0]) & 0x3FFF
                h = (struct.unpack_from("<H", chunk_data, 8)[0]) & 0x3FFF
                result["width"] = w
                result["height"] = h
            elif chunk_id == b"VP8L" and len(chunk_data) >= 5:
                # Lossless: 14-bit width-1 and 14-bit height-1
                bits = struct.unpack_from("<I", chunk_data, 1)[0]
                result["width"] = (bits & 0x3FFF) + 1
                result["height"] = ((bits >> 14) & 0x3FFF) + 1
            elif chunk_id == b"VP8X" and len(chunk_data) >= 10:
                result["width"] = (struct.unpack_from("<I", chunk_data, 4)[0] & 0xFFFFFF) + 1
                result["height"] = (struct.unpack_from("<I", chunk_data, 7)[0] & 0xFFFFFF) + 1
            elif chunk_id == b"EXIF":
                exif_data = _parse_exif_comfy_data(chunk_data)
                result["metadata_json"].update(exif_data)
            elif chunk_id == b"XMP " or chunk_id == b"XMP\x00":
                # XMP is UTF-8 text; some tools embed ComfyUI JSON inside XMP description
                xmp_text = chunk_data.decode("utf-8", errors="ignore")
                result["metadata_json"]["xmp_raw"] = xmp_text
                # Try to extract JSON blob from XMP
                for candidate_start in ("{{", "{"):
                    start_idx = xmp_text.find(candidate_start)
                    if start_idx != -1:
                        try:
                            parsed = json.loads(xmp_text[start_idx:])
                            if isinstance(parsed, dict) and any(k in parsed for k in ("prompt", "workflow")):
                                result["metadata_json"].update(parsed)
                                break
                        except json.JSONDecodeError:
                            pass

    return _finalize_metadata(result)


def _extract_avif_metadata(path: Path, result: dict[str, Any]) -> dict[str, Any]:
    """Extract ComfyUI metadata from an AVIF file via EXIF and XMP boxes."""
    with path.open("rb") as handle:
        data = handle.read()

    offset = 0
    while offset + 8 <= len(data):
        box_size = struct.unpack_from(">I", data, offset)[0]
        box_type = data[offset + 4: offset + 8]
        if box_size == 0:
            break
        box_data = data[offset + 8: offset + box_size]

        if box_type == b"ftyp":
            # Validate it's AVIF
            if b"avif" not in box_data and b"avis" not in box_data:
                return result
        elif box_type == b"Exif":
            exif_data = _parse_exif_comfy_data(box_data)
            result["metadata_json"].update(exif_data)
            # Also try to read width/height from EXIF tags 0xA002/0xA003
        elif box_type in (b"xml ", b"XMP "):
            xmp_text = box_data.decode("utf-8", errors="ignore")
            start_idx = xmp_text.find("{")
            if start_idx != -1:
                try:
                    parsed = json.loads(xmp_text[start_idx:])
                    if isinstance(parsed, dict) and any(k in parsed for k in ("prompt", "workflow")):
                        result["metadata_json"].update(parsed)
                except json.JSONDecodeError:
                    pass

        if offset + box_size <= offset:
            break
        offset += box_size

    return _finalize_metadata(result)


def read_workflow_from_file(path: Path) -> dict[str, Any] | list[Any] | None:
    """Read only the workflow JSON from the source file on-demand (not stored in DB)."""
    try:
        meta = extract_comfy_metadata(path)
        return meta.get("workflow_json")
    except Exception:
        LOGGER.warning("Failed to read workflow from %s", path)
        return None
