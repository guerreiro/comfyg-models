"""Watchdog integration for real-time filesystem changes."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger(__name__)

try:
    from watchdog.observers import Observer  # type: ignore

    HAS_WATCHDOG = True
except ImportError:
    Observer = None
    HAS_WATCHDOG = False


@dataclass
class ModelWatcher:
    """Minimal watcher scaffold to be expanded in Phase 1."""

    root: Path

    def start(self) -> None:
        """Start the filesystem watcher when watchdog is available."""
        if not HAS_WATCHDOG or Observer is None:
            LOGGER.warning("watchdog is not installed; file watching is disabled")
            return
        LOGGER.info("Model watcher scaffold ready for %s", self.root)

    def stop(self) -> None:
        """Stop the filesystem watcher scaffold."""
        LOGGER.info("Model watcher stop requested for %s", self.root)
