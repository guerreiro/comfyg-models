"""Helpers for indexing images into tags and visible filter values."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_PROMPT_SPLIT_RE = re.compile(r"\s*,\s*")
_LOW_SIGNAL_PROMPT_TERMS = {
    "masterpiece",
    "best quality",
    "high quality",
    "absurdres",
    "highres",
    "1girl",
    "1boy",
}


def _clean_value(value: str) -> str:
    return " ".join(value.strip().split())


def normalize_filter_value(filter_type: str, value: str) -> str | None:
    """Normalize a visible filter value for stable storage and display."""
    cleaned = _clean_value(value)
    if not cleaned:
        return None

    if filter_type in {"model", "lora"}:
        filename = Path(cleaned).name
        stem = Path(filename).stem
        return stem or filename or cleaned

    if filter_type == "base_model":
        return cleaned

    return cleaned


def build_filter_values(metadata: dict[str, Any]) -> list[tuple[str, str]]:
    """Build visible metadata-derived filter values."""
    values: set[tuple[str, str]] = set()

    for model_ref in metadata.get("model_refs", []):
        normalized = normalize_filter_value("model", str(model_ref))
        if normalized:
            values.add(("model", normalized))

    for lora_ref in metadata.get("lora_refs", []):
        normalized = normalize_filter_value("lora", str(lora_ref))
        if normalized:
            values.add(("lora", normalized))

    for base_model in metadata.get("base_model_refs", []):
        normalized = normalize_filter_value("base_model", str(base_model))
        if normalized:
            values.add(("base_model", normalized))

    return sorted(values)


def extract_prompt_terms(prompt_text: str | None) -> list[str]:
    """Extract low-noise prompt terms for search support."""
    if not prompt_text:
        return []

    terms: dict[str, str] = {}
    for raw_term in _PROMPT_SPLIT_RE.split(prompt_text):
        cleaned = _clean_value(raw_term)
        normalized = cleaned.lower()
        if not cleaned or len(normalized) < 3 or len(normalized) > 80:
            continue
        if normalized in _LOW_SIGNAL_PROMPT_TERMS:
            continue
        if normalized.startswith("{") or normalized.startswith("["):
            continue
        if normalized.count(":") > 2:
            continue
        if normalized.replace(".", "", 1).isdigit():
            continue
        terms.setdefault(normalized, cleaned)
    return sorted(terms.keys())


def build_image_tags(
    *,
    source_type: str,
    metadata: dict[str, Any],
    unresolved_models: list[str],
    scan_root: Path | None,
    file_path: Path | None,
) -> list[tuple[str, str]]:
    """Build automatic tags used for generic search and image detail display."""
    tags: set[tuple[str, str]] = set()
    tags.add((f"source:{source_type}", "source"))
    tags.add(("metadata:comfy" if metadata.get("has_comfy_metadata") else "metadata:none", "metadata"))

    for base_model in metadata.get("base_model_refs", []):
        normalized = normalize_filter_value("base_model", str(base_model))
        if normalized:
            tags.add((normalized, "base_model"))

    for model_ref in metadata.get("model_refs", []):
        normalized = normalize_filter_value("model", str(model_ref))
        if normalized:
            tags.add((normalized, "model_name"))

    for lora_ref in metadata.get("lora_refs", []):
        normalized = normalize_filter_value("lora", str(lora_ref))
        if normalized:
            tags.add((normalized, "lora_name"))

    for unresolved in unresolved_models:
        normalized = normalize_filter_value("model", unresolved)
        if normalized:
            tags.add((normalized, "missing_model"))

    for prompt_term in extract_prompt_terms(metadata.get("prompt_text")):
        tags.add((prompt_term, "prompt_term"))

    if scan_root is not None and file_path is not None:
        try:
            relative_parent = file_path.parent.relative_to(scan_root)
            if str(relative_parent) not in {".", ""}:
                tags.add((relative_parent.as_posix(), "folder"))
        except ValueError:
            pass

    return sorted(tags)
