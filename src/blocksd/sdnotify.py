"""Lightweight sd_notify — systemd notification via socket.

No external dependency required. Uses the NOTIFY_SOCKET environment variable
set by systemd when Type=notify is configured.
"""

from __future__ import annotations

import logging
import os
import socket

log = logging.getLogger(__name__)

_socket: socket.socket | None = None
_address: str | None = None


def _init() -> bool:
    """Initialize the notification socket (lazy, once)."""
    global _socket, _address

    if _socket is not None:
        return True

    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return False

    # Abstract socket (starts with @) or path socket
    if addr.startswith("@"):
        addr = "\0" + addr[1:]

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.connect(addr)
        _socket = sock
        _address = addr
    except OSError:
        log.debug("Failed to connect to NOTIFY_SOCKET")
        return False
    else:
        return True


def notify(state: str) -> bool:
    """Send a notification to systemd.

    Common states:
        READY=1     — service startup complete
        WATCHDOG=1  — watchdog keepalive
        STOPPING=1  — service shutting down
        STATUS=...  — free-form status string
    """
    if not _init():
        return False

    assert _socket is not None
    try:
        _socket.sendall(state.encode())
    except OSError:
        return False
    else:
        return True


def ready() -> bool:
    """Signal that the service is ready."""
    return notify("READY=1")


def stopping() -> bool:
    """Signal that the service is stopping."""
    return notify("STOPPING=1")


def watchdog() -> bool:
    """Send a watchdog keepalive."""
    return notify("WATCHDOG=1")


def status(msg: str) -> bool:
    """Set the service status text."""
    return notify(f"STATUS={msg}")


def watchdog_usec() -> int | None:
    """Get the watchdog interval from systemd, or None if not configured."""
    val = os.environ.get("WATCHDOG_USEC")
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return None
