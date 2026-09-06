"""Topology manager — top-level coordinator that scans for devices and manages groups."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from blocksd.device.connection import open_connection
from blocksd.protocol.constants import DEVICE_SCAN_INTERVAL_S
from blocksd.topology.detector import MidiPortPair, scan_for_blocks
from blocksd.topology.device_group import DeviceGroup

if TYPE_CHECKING:
    from collections.abc import Callable

    from blocksd.device.models import (
        ButtonEvent,
        ConfigValue,
        DeviceInfo,
        Topology,
        TouchEvent,
    )

log = logging.getLogger(__name__)


class TopologyManager:
    """Scans for ROLI MIDI devices, creates DeviceGroups, manages lifecycle.

    This is the main entry point for the connection layer. Call `run()` as an
    asyncio task — it will continuously scan for devices and manage their
    lifecycle until cancelled.
    """

    def __init__(self) -> None:
        self._groups: dict[str, _GroupEntry] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._running_tasks: set[asyncio.Task[None]] = set()
        self.on_device_added: list[Callable[[DeviceInfo], None]] = []
        self.on_device_removed: list[Callable[[DeviceInfo], None]] = []
        self.on_topology_changed: list[Callable[[Topology], None]] = []
        self.on_touch_event: list[Callable[[TouchEvent], None]] = []
        self.on_button_event: list[Callable[[ButtonEvent], None]] = []
        self.on_config_changed: list[Callable[[int, ConfigValue], None]] = []

    async def run(self) -> None:
        """Main scan loop — runs until cancelled."""
        log.info("Topology manager started")
        try:
            while True:
                await self._scan_cycle()
                await asyncio.sleep(DEVICE_SCAN_INTERVAL_S)
        finally:
            await self._shutdown()
            log.info("Topology manager stopped")

    @property
    def devices(self) -> list[DeviceInfo]:
        """All currently connected devices across all groups."""
        result: list[DeviceInfo] = []
        for entry in self._groups.values():
            result.extend(entry.group.topology.devices)
        return result

    @property
    def groups(self) -> list[DeviceGroup]:
        return [entry.group for entry in self._groups.values()]

    def set_led_data(self, uid: int, pixel_data: bytes | bytearray) -> bool:
        """Write LED pixel data to a device across all groups.

        Returns True if the write was accepted by any group.
        """
        return any(entry.group.set_led_data(uid, pixel_data) for entry in self._groups.values())

    def find_device(self, uid: int) -> DeviceInfo | None:
        """Find a device by UID across all groups."""
        for entry in self._groups.values():
            for dev in entry.group.topology.devices:
                if dev.uid == uid:
                    return dev
        return None

    def get_config(self, uid: int) -> dict[int, ConfigValue]:
        """Get all known config values for a device."""
        for entry in self._groups.values():
            cfg = entry.group.get_config(uid)
            if cfg:
                return cfg
        return {}

    def set_config(self, uid: int, item: int, value: int) -> bool:
        """Set a config value on a device."""
        return any(entry.group.set_config(uid, item, value) for entry in self._groups.values())

    # ── Scan cycle ────────────────────────────────────────────────────────

    async def _scan_cycle(self) -> None:
        """One iteration of the scan/prune loop."""
        try:
            detected = await asyncio.get_event_loop().run_in_executor(None, scan_for_blocks)
        except Exception:
            log.exception("MIDI scan failed")
            return

        detected_keys = {pair.key for pair in detected}

        # Remove groups whose ports disappeared
        stale = [key for key in self._groups if key not in detected_keys]
        retiring = [self._tasks[key] for key in stale if key in self._tasks]
        for key in stale:
            self._remove_group(key)
        # Release disappeared endpoints before opening newly discovered devices.
        await asyncio.gather(*retiring, return_exceptions=True)

        # Add groups for newly detected ports
        for pair in detected:
            if pair.key not in self._groups:
                self._add_group(pair)

    def _add_group(self, pair: MidiPortPair) -> None:
        """Create a DeviceGroup for a newly detected MIDI port pair."""
        loop = asyncio.get_event_loop()
        try:
            conn = open_connection(
                pair.input_port,
                pair.output_port,
                loop,
                name=pair.name,
                endpoint_ids=pair.endpoint_ids,
            )
        except Exception:
            log.exception("Failed to open MIDI ports for %s", pair.name)
            return

        group = DeviceGroup(conn)
        group.on_device_added = self.on_device_added
        group.on_device_removed = self.on_device_removed
        group.on_topology_changed = self.on_topology_changed
        group.on_touch_event = self.on_touch_event
        group.on_button_event = self.on_button_event
        group.on_config_changed = self.on_config_changed

        task = asyncio.create_task(group.run(), name=f"group:{pair.name}")
        self._running_tasks.add(task)
        task.add_done_callback(lambda t, key=pair.key: self._on_group_done(key, t))

        self._groups[pair.key] = _GroupEntry(group, pair)
        self._tasks[pair.key] = task
        log.info("Created device group for %s", pair.name)

    def _remove_group(self, key: str) -> None:
        """Cancel and clean up a device group."""
        if task := self._tasks.pop(key, None):
            task.cancel()
        entry = self._groups.pop(key, None)
        log.info("Removed device group for %s", entry.pair.name if entry else key)

    def _on_group_done(self, key: str, task: asyncio.Task[None]) -> None:
        """Handle a group task completing (disconnection or failure)."""
        self._running_tasks.discard(task)
        # A disconnected port may already have a replacement group by this point.
        if self._tasks.get(key) is task:
            self._groups.pop(key, None)
            self._tasks.pop(key, None)
        if task.cancelled():
            return
        if error := task.exception():
            log.error("Device group %s failed: %s", key, error)
        else:
            log.info("Device group %s finished", key)

    async def _shutdown(self) -> None:
        """Join active and retiring groups before relinquishing MIDI ownership."""
        tasks = list(self._running_tasks)
        for task in tasks:
            if not task.cancelling():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._groups.clear()
        self._tasks.clear()
        self._running_tasks.clear()


class _GroupEntry:
    __slots__ = ("group", "pair")

    def __init__(self, group: DeviceGroup, pair: MidiPortPair) -> None:
        self.group = group
        self.pair = pair
