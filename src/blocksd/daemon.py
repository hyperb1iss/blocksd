"""Main daemon — asyncio event loop, signal handling, device lifecycle."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from pathlib import Path
from typing import TYPE_CHECKING

from blocksd import sdnotify
from blocksd.api.server import ApiServer, WebServer
from blocksd.config.schema import DaemonConfig
from blocksd.logging import setup_logging
from blocksd.topology.manager import TopologyManager

if TYPE_CHECKING:
    from collections.abc import Sequence

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

    # Start API server for Hypercolor integration
    socket_path = Path(config.api_socket) if config.api_socket else None
    api_server = ApiServer(manager, socket_path=socket_path)

    # Start web UI server
    web_server = WebServer(
        manager,
        host=config.web_host,
        port=config.web_port,
    )

    # Graceful shutdown on SIGINT/SIGTERM
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    async with contextlib.AsyncExitStack() as cleanup:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
            cleanup.callback(loop.remove_signal_handler, sig)

        # Register cleanup before startup so partial initialization is unwound too.
        if config.api_enabled:
            cleanup.push_async_callback(api_server.stop)
            await api_server.start()
        if config.web_enabled:
            cleanup.push_async_callback(web_server.stop)
            await web_server.start()

        manager_task = asyncio.create_task(manager.run(), name="topology-manager")
        stop_task = asyncio.create_task(stop_event.wait(), name="shutdown-signal")
        tasks = [manager_task, stop_task]
        cleanup.push_async_callback(_cancel_tasks, tasks)
        watchdog_task = _start_watchdog(stop_event)
        if watchdog_task is not None:
            tasks.append(watchdog_task)

        sdnotify.ready()
        sdnotify.status("Scanning for ROLI devices")
        log.info("blocksd ready: scanning for ROLI devices")
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task is not stop_task:
                    await task
                    if not stop_event.is_set():
                        raise RuntimeError(f"Daemon task {task.get_name()} stopped unexpectedly")
        finally:
            sdnotify.stopping()
            log.info("Shutting down...")

    log.info("blocksd stopped")


async def _cancel_tasks(tasks: Sequence[asyncio.Task[object]]) -> None:
    """Join every owned task before releasing servers and signal handlers."""
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


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
