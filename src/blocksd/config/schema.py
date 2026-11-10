"""Pydantic config schema for blocksd."""

from __future__ import annotations

import sys

from pydantic import BaseModel, Field


class DaemonConfig(BaseModel):
    """Top-level daemon configuration."""

    scan_interval: float = 1.5
    ping_interval_master: float = 0.4
    ping_interval_dna: float = 1.666
    api_ping_timeout: float = 6.0
    verbose: bool = False

    # Unix socket API; Windows commands use the web server's WebSocket endpoint.
    api_enabled: bool = Field(default_factory=lambda: sys.platform != "win32")
    api_socket: str = ""  # empty = platform-specific local socket path

    # Web UI settings
    web_enabled: bool = True
    web_host: str = "127.0.0.1"
    web_port: int = 9010
