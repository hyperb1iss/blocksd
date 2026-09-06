"""Config file discovery and loading."""

from __future__ import annotations

import logging
import tomllib
from typing import TYPE_CHECKING

from blocksd.config.schema import DaemonConfig
from blocksd.paths import config_paths

if TYPE_CHECKING:
    from pathlib import Path

log = logging.getLogger(__name__)


def load_config(path: Path | None = None) -> DaemonConfig:
    """Load config from file, falling back to defaults.

    An explicit path takes priority over platform-specific defaults.
    """
    if path and path.exists():
        return _parse_config(path)

    for candidate in config_paths():
        if candidate.exists():
            return _parse_config(candidate)

    log.debug("No config file found, using defaults")
    return DaemonConfig()


def _parse_config(path: Path) -> DaemonConfig:
    """Parse a TOML config file into DaemonConfig."""
    log.info("Loading config from %s", path)
    with path.open("rb") as f:
        data = tomllib.load(f)
    return DaemonConfig(**data.get("daemon", data))
