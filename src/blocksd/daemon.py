"""Main daemon — asyncio event loop, signal handling, device lifecycle."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from typing import TYPE_CHECKING

from blocksd import sdnotify
from blocksd.config.schema import DaemonConfig
from blocksd.logging import setup_logging
from blocksd.topology.manager import TopologyManager

if TYPE_CHECKING:
    from blocksd.device.models import ButtonEvent, DeviceInfo, Topology, TouchEvent

log = logging.getLogger(__name__)


async def run_daemon(config: DaemonConfig) -> None:
    """Main daemon coroutine — manages ROLI Blocks devices until shutdown."""
    setup_logging(verbose=config.verbose)
    log.info("blocksd starting")

    manager = TopologyManager()
    manager.on_device_added.append(_on_device_added)
    manager.on_device_removed.append(_on_device_removed)
    manager.on_topology_changed.append(_on_topology_changed)
    manager.on_touch_event.append(_on_touch)
    manager.on_button_event.append(_on_button)

    # Graceful shutdown on SIGINT/SIGTERM
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    manager_task = asyncio.create_task(manager.run(), name="topology-manager")
    watchdog_task = _start_watchdog(stop_event)

    sdnotify.ready()
    sdnotify.status("Scanning for ROLI devices")
    log.info("blocksd ready — scanning for ROLI devices")
    await stop_event.wait()

    sdnotify.stopping()
    log.info("Shutting down...")
    manager_task.cancel()
    if watchdog_task:
        watchdog_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await manager_task
    if watchdog_task:
        with contextlib.suppress(asyncio.CancelledError):
            await watchdog_task

    log.info("blocksd stopped")


def _start_watchdog(stop_event: asyncio.Event) -> asyncio.Task[None] | None:
    """Start a watchdog heartbeat task if systemd requests it."""
    usec = sdnotify.watchdog_usec()
    if usec is None:
        return None
    # Ping at half the watchdog interval (recommended by systemd docs)
    interval = usec / 1_000_000 / 2
    log.info("Watchdog enabled (interval=%.1fs)", interval)

    async def heartbeat() -> None:
        while not stop_event.is_set():
            sdnotify.watchdog()
            await asyncio.sleep(interval)

    return asyncio.create_task(heartbeat(), name="watchdog")


def start(config: DaemonConfig | None = None) -> None:
    """Entry point — run the daemon with asyncio."""
    if config is None:
        config = DaemonConfig()
    asyncio.run(run_daemon(config))


# ── Event handlers ────────────────────────────────────────────────────────────


def _on_device_added(dev: DeviceInfo) -> None:
    log.info(
        "✨ Device connected: %s (%s) — battery %d%%",
        dev.block_type,
        dev.serial,
        dev.battery_level,
    )
    sdnotify.status(f"Connected: {dev.block_type}")


def _on_device_removed(dev: DeviceInfo) -> None:
    log.info("👋 Device disconnected: %s (%s)", dev.block_type, dev.serial)


def _on_topology_changed(topo: Topology) -> None:
    log.info(
        "🔗 Topology: %d devices, %d connections",
        len(topo.devices),
        len(topo.connections),
    )
    sdnotify.status(f"{len(topo.devices)} device(s) connected")


def _on_touch(event: TouchEvent) -> None:
    log.debug(
        "👆 Touch %s idx=%d (%.2f, %.2f) z=%.2f",
        "start" if event.is_start else ("end" if event.is_end else "move"),
        event.touch_index,
        event.x,
        event.y,
        event.z,
    )


def _on_button(event: ButtonEvent) -> None:
    log.debug(
        "🔘 Button %d %s",
        event.button_id,
        "down" if event.is_down else "up",
    )
