"""Platform-specific locations for configuration and local IPC."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def config_paths() -> list[Path]:
    """Return configuration candidates in descending priority order."""
    user_config = Path.home() / ".config" / "blocksd" / "config.toml"
    if sys.platform == "darwin":
        return [
            Path.home() / "Library" / "Application Support" / "blocksd" / "config.toml",
            user_config,
            Path("/etc/blocksd/config.toml"),
        ]
    return [user_config, Path("/etc/blocksd/config.toml")]


def default_socket_path() -> Path:
    """Return a short socket path, independent of macOS's long TMPDIR."""
    if sys.platform == "darwin":
        return Path(f"/tmp/blocksd-{os.getuid()}/blocksd.sock")  # noqa: S108
    if runtime_dir := os.environ.get("XDG_RUNTIME_DIR"):
        return Path(runtime_dir) / "blocksd" / "blocksd.sock"
    return Path("/tmp/blocksd/blocksd.sock")  # noqa: S108
