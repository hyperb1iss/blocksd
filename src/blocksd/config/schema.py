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

    # API server settings
    api_enabled: bool = True
    api_socket: str = ""  # empty = default ($XDG_RUNTIME_DIR/blocksd/blocksd.sock)

    # Web UI settings
    web_enabled: bool = True
    web_host: str = "127.0.0.1"
    web_port: int = 9010


DEFAULT_CONFIG_PATHS = [
    Path("/etc/blocksd/config.toml"),
    Path.home() / ".config" / "blocksd" / "config.toml",
]
