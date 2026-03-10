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

    from blocksd.device.models import DeviceInfo, Topology

log = logging.getLogger(__name__)


class TopologyManager:
    """Scans for ROLI MIDI devices, creates DeviceGroups, manages lifecycle.

    This is the main entry point for the connection layer. Call `run()` as an
    asyncio task — it will continuously scan for devices and manage their
    lifecycle until cancelled.
    """

    def __init__(self) -> None:
        self._groups: dict[str, _GroupEntry] = {}  # port name → entry
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self.on_device_added: list[Callable[[DeviceInfo], None]] = []
        self.on_device_removed: list[Callable[[DeviceInfo], None]] = []
        self.on_topology_changed: list[Callable[[Topology], None]] = []

    async def run(self) -> None:
        """Main scan loop — runs until cancelled."""
        log.info("Topology manager started")
        try:
            while True:
                await self._scan_cycle()
                await asyncio.sleep(DEVICE_SCAN_INTERVAL_S)
        except asyncio.CancelledError:
            pass
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

    # ── Scan cycle ────────────────────────────────────────────────────────

    async def _scan_cycle(self) -> None:
        """One iteration of the scan/prune loop."""
        try:
            detected = await asyncio.get_event_loop().run_in_executor(None, scan_for_blocks)
        except Exception:
            log.exception("MIDI scan failed")
            return

        detected_names = {pair.name for pair in detected}

        # Remove groups whose ports disappeared
        stale = [name for name in self._groups if name not in detected_names]
        for name in stale:
            self._remove_group(name)

        # Add groups for newly detected ports
        for pair in detected:
            if pair.name not in self._groups:
                self._add_group(pair)

    def _add_group(self, pair: MidiPortPair) -> None:
        """Create a DeviceGroup for a newly detected MIDI port pair."""
        loop = asyncio.get_event_loop()
        try:
            conn = open_connection(pair.input_port, pair.output_port, loop, name=pair.name)
        except Exception:
            log.exception("Failed to open MIDI ports for %s", pair.name)
            return

        group = DeviceGroup(conn)
        group.on_device_added = list(self.on_device_added)
        group.on_device_removed = list(self.on_device_removed)
        group.on_topology_changed = list(self.on_topology_changed)

        task = asyncio.create_task(group.run(), name=f"group:{pair.name}")
        task.add_done_callback(lambda t, n=pair.name: self._on_group_done(n, t))

        self._groups[pair.name] = _GroupEntry(group, pair)
        self._tasks[pair.name] = task
        log.info("Created device group for %s", pair.name)

    def _remove_group(self, name: str) -> None:
        """Cancel and clean up a device group."""
        if task := self._tasks.pop(name, None):
            task.cancel()
        self._groups.pop(name, None)
        log.info("Removed device group for %s", name)

    def _on_group_done(self, name: str, task: asyncio.Task[None]) -> None:
        """Handle a group task completing (disconnection or failure)."""
        self._groups.pop(name, None)
        self._tasks.pop(name, None)
        if task.exception():
            log.error("Device group %s failed: %s", name, task.exception())
        else:
            log.info("Device group %s finished", name)

    async def _shutdown(self) -> None:
        """Cancel all group tasks and wait for cleanup."""
        for task in self._tasks.values():
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._groups.clear()
        self._tasks.clear()


class _GroupEntry:
    __slots__ = ("group", "pair")

    def __init__(self, group: DeviceGroup, pair: MidiPortPair) -> None:
        self.group = group
        self.pair = pair
