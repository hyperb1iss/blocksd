"""Pydantic config schema for blocksd."""

from __future__ import annotations

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
    api_socket: str = ""  # empty = platform-specific local socket path

    # Web UI settings
    web_enabled: bool = True
    web_host: str = "127.0.0.1"
    web_port: int = 9010
