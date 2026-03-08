"""Pydantic config schema for blocksd."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class DaemonConfig(BaseModel):
    """Top-level daemon configuration."""

    scan_interval: float = 1.5
    ping_interval_master: float = 0.4
    ping_interval_dna: float = 1.666
    api_ping_timeout: float = 6.0
    verbose: bool = False


DEFAULT_CONFIG_PATHS = [
    Path("/etc/blocksd/config.toml"),
    Path.home() / ".config" / "blocksd" / "config.toml",
]
