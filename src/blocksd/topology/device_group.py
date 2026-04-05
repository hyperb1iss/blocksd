"""Connected device group — manages the full lifecycle for one USB connection.

Ported from roli_ConnectedDeviceGroup.cpp.
Handles: topology request → API mode activation → periodic ping → timeout.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import TYPE_CHECKING

from blocksd.device.models import (
    ButtonEvent,
    ConfigValue,
    DeviceConnection,
    DeviceInfo,
    Topology,
    TouchEvent,
)
from blocksd.device.registry import (
    block_type_from_serial,
    heap_size_for_block,
    supports_bitmap_led_program,
)
from blocksd.littlefoot.programs import bitmap_led_program_size
from blocksd.protocol.builder import (
    build_begin_api_mode,
    build_config_request,
    build_end_api_mode,
    build_ping,
    build_request_topology,
)
from blocksd.protocol.constants import SERIAL_DUMP_REQUEST
from blocksd.protocol.decoder import decode_packet
from blocksd.protocol.remote_heap import RemoteHeap
from blocksd.protocol.serial import is_serial_response, parse_serial_response

if TYPE_CHECKING:
    from collections.abc import Callable

    from blocksd.device.connection import MidiConnection

log = logging.getLogger(__name__)

# ── Timing constants ──────────────────────────────────────────────────────────

TOPOLOGY_REQUEST_INTERVAL = 1.0  # seconds between topology requests
TOPOLOGY_TIMEOUT = 30.0  # give up after this long without topology
MAX_TOPOLOGY_REQUESTS = 4
API_PING_TIMEOUT = 6.0  # seconds before device considered disconnected (C++ pingTimeoutSeconds)
MASTER_PING_INTERVAL = 0.4  # 400ms for master block
DNA_PING_INTERVAL = 1.666  # ~1666ms for DNA-connected blocks
SERIAL_REQUEST_INTERVAL = 0.3  # 300ms between serial dump requests
SERIAL_TIMEOUT = 5.0  # give up serial after 5s
TICK_INTERVAL = 0.2  # 200ms lifecycle timer (matches C++ timerInterval)


def _build_green_fill() -> bytes:
    """Fill 15x15 grid with green — fully unrolled, no loops or dupOffset.

    Emits 225 hardcoded fillPixel calls. Large but guaranteed to work
    since it only uses opcodes proven safe on firmware v1.1.0.
    """
    from blocksd.littlefoot.assembler import BytecodeAssembler, compute_function_id

    make_argb = compute_function_id("makeARGB/iiiii")
    fill_pixel = compute_function_id("fillPixel/viii")

    asm = BytecodeAssembler(heap_size=0)
    asm.begin_function("repaint/v")

    for y in range(15):
        for x in range(15):
            # fillPixel(makeARGB(255, 0, 255, 0), x, y) — all args hardcoded
            asm.push8(y)  # y (RTL: pushed first)
            asm.push8(x)  # x
            asm.push0()  # blue = 0
            asm.push16(255)  # green = 255
            asm.push0()  # red = 0
            asm.push16(255)  # alpha = 255
            asm.call_native(make_argb)
            asm.call_native(fill_pixel)

    asm.ret_void(0)
    return asm.build()


class GroupState(StrEnum):
    REQUESTING_SERIAL = auto()
    REQUESTING_TOPOLOGY = auto()
    RUNNING = auto()
    FAILED = auto()


@dataclass
class PingEntry:
    """Tracks API connection status for a single device."""

    uid: int
    last_ack: float
    last_ping_sent: float
    connected_at: float


class DeviceGroup:
    """Manages the full lifecycle for devices on a single MIDI connection.

    Implements the PacketHandler protocol to receive decoded device messages.
    """

    def __init__(self, conn: MidiConnection) -> None:
        self.conn = conn
        self.state = GroupState.REQUESTING_SERIAL
        self.topology = Topology()
        self.master_uid: int = 0
        self.master_serial: str = ""

        # Topology tracking
        self._incoming_devices: list[_IncomingDevice] = []
        self._incoming_connections: list[_IncomingConnection] = []
        self._devices: dict[int, DeviceInfo] = {}  # uid → DeviceInfo
        self._pings: dict[int, PingEntry] = {}  # uid → PingEntry
        self._end_api_sent: set[int] = set()  # UIDs that received endAPIMode this session
        self._heaps: dict[int, RemoteHeap] = {}  # uid → RemoteHeap
        self._config: dict[int, dict[int, ConfigValue]] = {}  # uid → {item → ConfigValue}

        # Timing
        self._last_topology_request = 0.0
        self._last_topology_received = 0.0
        self._topology_requests_sent = 0
        self._last_serial_request = 0.0
        self._serial_start_time = 0.0

        # Callbacks (set by TopologyManager)
        self.on_device_added: list[Callable[[DeviceInfo], None]] = []
        self.on_device_removed: list[Callable[[DeviceInfo], None]] = []
        self.on_topology_changed: list[Callable[[Topology], None]] = []
        self.on_touch_event: list[Callable[[TouchEvent], None]] = []
        self.on_button_event: list[Callable[[ButtonEvent], None]] = []
        self.on_config_changed: list[Callable[[int, ConfigValue], None]] = []

    async def run(self) -> None:
        """Main lifecycle loop — runs until connection closes or failure."""
        self._serial_start_time = time.monotonic()
        self._send_serial_request()
        self._send_topology_request()

        try:
            while self.state != GroupState.FAILED and self.conn.is_open:
                await self._tick()
                await asyncio.sleep(TICK_INTERVAL)
        except asyncio.CancelledError:
            pass
        finally:
            self._remove_all_devices()
            self.conn.close()

    # ── Packet processing ─────────────────────────────────────────────────

    async def _tick(self) -> None:
        """Process incoming messages + run lifecycle timer."""
        # Drain all pending messages
        for msg in self.conn.drain():
            self._process_message(msg)

        # Also try async recv with short timeout for any stragglers
        while True:
            msg = await self.conn.recv(timeout=0.01)
            if msg is None:
                break
            self._process_message(msg)

        now = time.monotonic()
        self._lifecycle_timer(now)

    def _process_message(self, data: bytes) -> None:
        """Route an incoming SysEx message."""
        if is_serial_response(data):
            self._handle_serial_response(data)
        else:
            decode_packet(data, self)

    # ── Serial handling ───────────────────────────────────────────────────

    def _send_serial_request(self) -> None:
        self.conn.send(SERIAL_DUMP_REQUEST)
        self._last_serial_request = time.monotonic()

    def _handle_serial_response(self, data: bytes) -> None:
        serial = parse_serial_response(data)
        if serial and not self.master_serial:
            self.master_serial = serial
            log.info("Master serial: %s", serial)
            if self.state == GroupState.REQUESTING_SERIAL:
                self.state = GroupState.REQUESTING_TOPOLOGY

    # ── Lifecycle timer ───────────────────────────────────────────────────

    def _lifecycle_timer(self, now: float) -> None:
        match self.state:
            case GroupState.REQUESTING_SERIAL:
                self._tick_serial(now)
            case GroupState.REQUESTING_TOPOLOGY:
                self._tick_topology(now)
            case GroupState.RUNNING:
                self._tick_running(now)

    def _tick_serial(self, now: float) -> None:
        if now - self._serial_start_time > SERIAL_TIMEOUT:
            # Serial optional — proceed without it
            log.warning("Serial timeout, proceeding without master serial")
            self.state = GroupState.REQUESTING_TOPOLOGY
            return
        if now - self._last_serial_request > SERIAL_REQUEST_INTERVAL:
            self._send_serial_request()

    def _tick_topology(self, now: float) -> None:
        should_request = (
            now - self._last_topology_received > TOPOLOGY_TIMEOUT
            and now - self._last_topology_request > TOPOLOGY_REQUEST_INTERVAL
            and self._topology_requests_sent < MAX_TOPOLOGY_REQUESTS
        )
        if should_request:
            self._send_topology_request()

        if self._topology_requests_sent >= MAX_TOPOLOGY_REQUESTS and not self._devices:
            log.error("Failed to get topology from %s", self.conn.name)
            self.state = GroupState.FAILED

    def _tick_running(self, now: float) -> None:
        # Topology re-request: matches C++ timerCallback condition exactly.
        # _schedule_topology_request() resets _last_topology_received to 0.0,
        # making this fire immediately (with 1s cooldown) after a device timeout.
        if (
            now - self._last_topology_received > TOPOLOGY_TIMEOUT
            and now - self._last_topology_request > TOPOLOGY_REQUEST_INTERVAL
            and self._topology_requests_sent < MAX_TOPOLOGY_REQUESTS
        ):
            self._send_topology_request()

        self._check_api_timeouts(now)
        self._start_api_on_unconnected()
        self._send_pings(now)
        self._flush_heaps(now)

    def _send_topology_request(self) -> None:
        self._topology_requests_sent += 1
        self._last_topology_request = time.monotonic()
        self.conn.send(build_request_topology(0))

    # ── API mode management ───────────────────────────────────────────────

    def _start_api_on_unconnected(self) -> None:
        """Send beginAPIMode to devices not yet API-connected.

        endAPIMode is sent exactly ONCE per device per group session to reset
        any stale state from a previous connection. It is never re-sent even
        if the device is removed and re-added (e.g. transient DNA topology
        glitch), because the device is likely still in API mode and endAPIMode
        would cause a visible LED reset.
        """
        for dev in self._devices.values():
            if dev.uid in self._pings:
                continue
            if dev.uid not in self._end_api_sent:
                log.debug(
                    "Activating API mode on %s (idx=%d)",
                    dev.serial,
                    dev.topology_index,
                )
                self.conn.send(build_end_api_mode(dev.topology_index))
                self._end_api_sent.add(dev.uid)
            self.conn.send(build_begin_api_mode(dev.topology_index))

    def _send_pings(self, now: float) -> None:
        """Send periodic pings to keep devices alive.

        Matches C++ BlockImplementation::handleTimerTick: ping interval is
        measured from last SEND time only (not ACK time). This keeps the
        cadence steady regardless of ACK latency — critical for DNA devices
        where the 5000ms device-side timeout is tight against the 1666ms interval.
        """
        for uid, ping in self._pings.items():
            dev = self._devices.get(uid)
            if dev is None:
                continue
            interval = MASTER_PING_INTERVAL if dev.is_master else DNA_PING_INTERVAL
            if now - ping.last_ping_sent > interval:
                self.conn.send(build_ping(dev.topology_index))
                ping.last_ping_sent = now

    def _check_api_timeouts(self, now: float) -> None:
        """Drop API connection for devices that haven't ACK'd within the timeout.

        Matches C++ checkApiTimeouts: removes the device fully and schedules
        a topology rediscovery so the device can be re-detected cleanly.
        """
        timed_out = [
            uid for uid, ping in self._pings.items() if now - ping.last_ack > API_PING_TIMEOUT
        ]
        for uid in timed_out:
            dev = self._devices.get(uid)
            log.warning("Ping timeout: device %s", dev.serial if dev else uid)
            self._remove_device(uid)
            self._schedule_topology_request()

    def _update_api_ping(self, uid: int) -> None:
        """Record an ACK from a device — marks it as API-connected."""
        now = time.monotonic()
        if uid in self._pings:
            self._pings[uid].last_ack = now
        else:
            log.info("Device API connected: %d", uid)
            self._pings[uid] = PingEntry(uid, last_ack=now, last_ping_sent=now, connected_at=now)
            dev = self._devices.get(uid)
            if dev:
                # Create a RemoteHeap and load LED program
                if uid not in self._heaps:
                    self._heaps[uid] = RemoteHeap(heap_size_for_block(dev.block_type))
                    self._load_led_program(uid)
                self._request_config_sync(uid)
                for cb in self.on_device_added:
                    cb(dev)

    def get_heap(self, uid: int) -> RemoteHeap | None:
        """Get the RemoteHeap for a device, or None if not API-connected."""
        return self._heaps.get(uid)

    def set_led_data(self, uid: int, pixel_data: bytes | bytearray) -> bool:
        """Write RGB565 LED pixel data to a device's heap.

        The data is written at the BitmapLEDProgram offset (after the program
        bytecode). Returns True if the write was accepted, False if the device
        has no heap or doesn't expose the upstream bitmap LED grid surface.
        """
        dev = self._devices.get(uid)
        heap = self._heaps.get(uid)
        if dev is None or heap is None or not supports_bitmap_led_program(dev.block_type):
            return False
        offset = bitmap_led_program_size()
        if offset + len(pixel_data) > heap.size:
            return False
        heap.set_bytes(offset, pixel_data)
        self._flush_heap(uid, heap, time.monotonic())
        return True

    def _load_led_program(self, uid: int) -> None:
        """Load LED test program into a device's heap.

        TODO: Replace with proper BitmapLEDProgram once firmware opcode
        compatibility is resolved (getHeapBits 0x40 and dupOffset_01 0x11
        are not supported on firmware v1.1.0).
        """
        dev = self._devices.get(uid)
        heap = self._heaps.get(uid)
        if dev is None or heap is None:
            return
        if not supports_bitmap_led_program(dev.block_type):
            return
        # TODO: Replace with proper BitmapLEDProgram using firmware-safe opcodes
        # For now, skip program upload — device keeps its default LED animation.
        return
        program = _build_green_fill()
        heap.set_bytes(0, program)
        log.debug("Loaded green fill program (%d bytes) for %s", len(program), dev.serial)

    def _flush_heaps(self, now: float) -> None:
        """Send pending heap changes and retransmit timed-out packets."""
        for uid, heap in self._heaps.items():
            self._flush_heap(uid, heap, now)

    def _flush_heap(self, uid: int, heap: RemoteHeap, now: float) -> None:
        """Flush one device heap immediately.

        send_changes() advances the optimistic state on each packet, so loop
        until the heap is clean or the in-flight budget blocks additional sends.
        """
        dev = self._devices.get(uid)
        if dev is None:
            return

        retransmit = heap.get_retransmit(now)
        if retransmit is not None:
            self.conn.send(retransmit)

        while True:
            packet = heap.send_changes(dev.topology_index, now)
            if packet is None:
                break
            self.conn.send(packet)

    # ── Config management ────────────────────────────────────────────────

    def get_config(self, uid: int) -> dict[int, ConfigValue]:
        """Get all known config values for a device."""
        return dict(self._config.get(uid, {}))

    def set_config(self, uid: int, item: int, value: int) -> bool:
        """Send a config set command to a device."""
        dev = self._devices.get(uid)
        if dev is None or uid not in self._pings:
            return False
        self.conn.send(build_config_request(dev.topology_index, item))
        from blocksd.protocol.builder import build_config_set

        self.conn.send(build_config_set(dev.topology_index, item, value))
        return True

    def _request_config_sync(self, uid: int) -> None:
        """Request a full config sync from a newly connected device."""
        dev = self._devices.get(uid)
        if dev is None:
            return
        from blocksd.protocol.builder import build_config_request_user_sync

        self.conn.send(build_config_request_user_sync(dev.topology_index))
        log.debug("Requested config sync for %s", dev.serial)

    # ── Device management ─────────────────────────────────────────────────

    def _uid_from_serial(self, serial: str) -> int:
        """Generate a deterministic 64-bit UID from the device serial."""
        digest = hashlib.blake2b(
            serial.encode("utf-8"),
            digest_size=8,
            person=b"blocksd",
        ).digest()
        return int.from_bytes(digest, "little")

    def _uid_from_index(self, topology_index: int) -> int:
        """Look up device UID by topology index.

        Matches C++ getDeviceIDFromIndex: schedules a topology re-request
        when an unknown index is received while running, indicating a
        topology change we haven't seen yet.
        """
        for dev in self._devices.values():
            if dev.topology_index == topology_index:
                return dev.uid
        if self.state == GroupState.RUNNING and self._devices:
            self._schedule_topology_request()
        return 0

    def _remove_device(self, uid: int) -> None:
        """Remove a device from tracking (preserves _end_api_sent guard)."""
        dev = self._devices.pop(uid, None)
        self._pings.pop(uid, None)
        self._heaps.pop(uid, None)
        self._config.pop(uid, None)
        # NOTE: _end_api_sent is intentionally NOT cleared here.
        # If the device reappears (e.g. transient DNA glitch), we skip
        # endAPIMode since the device is likely still in API mode.
        if dev:
            log.info("Device removed: %s", dev.serial)
            for cb in self.on_device_removed:
                cb(dev)

    def _remove_all_devices(self) -> None:
        for uid in list(self._devices):
            self._remove_device(uid)

    def _schedule_topology_request(self) -> None:
        self._topology_requests_sent = 0
        self._last_topology_received = 0.0

    def _rebuild_topology(self) -> None:
        """Rebuild the public Topology from current state."""
        self.topology = Topology(
            devices=list(self._devices.values()),
            connections=[
                DeviceConnection(
                    device1_uid=self._uid_from_index(c.dev1_idx),
                    device2_uid=self._uid_from_index(c.dev2_idx),
                    port1=c.port1,
                    port2=c.port2,
                )
                for c in self._incoming_connections
                if self._uid_from_index(c.dev1_idx) and self._uid_from_index(c.dev2_idx)
            ],
        )
        for cb in self.on_topology_changed:
            cb(self.topology)

    # ── PacketHandler implementation ──────────────────────────────────────

    def on_topology_begin(self, num_devices: int, num_connections: int) -> None:
        self._incoming_devices.clear()
        self._incoming_connections.clear()

    def on_topology_extend(self, num_devices: int, num_connections: int) -> None:
        pass  # incoming lists already accumulating

    def on_topology_device(
        self, topology_index: int, serial: str, battery_level: int, battery_charging: bool
    ) -> None:
        self._incoming_devices.append(
            _IncomingDevice(topology_index, serial, battery_level, battery_charging)
        )

    def on_topology_connection(self, dev1_idx: int, port1: int, dev2_idx: int, port2: int) -> None:
        self._incoming_connections.append(_IncomingConnection(dev1_idx, port1, dev2_idx, port2))

    def on_topology_end(self) -> None:
        self._last_topology_received = time.monotonic()
        # NOTE: _topology_requests_sent is NOT reset here — matches C++ endTopology.
        # Only _schedule_topology_request() resets it (on timeout or unknown index).
        # This gives us 4 total requests (initial + 3 periodic at 30s intervals),
        # then stops. Without this, we'd re-request topology every 30s forever.

        # C++ endTopology validation: devices must be non-empty and fully connected
        num_devs = len(self._incoming_devices)
        num_conns = len(self._incoming_connections)
        if num_devs == 0 or num_conns < num_devs - 1:
            log.warning(
                "Invalid topology: %d devices, %d connections (need >= %d), re-requesting",
                num_devs,
                num_conns,
                max(num_devs - 1, 0),
            )
            self._schedule_topology_request()
            return

        first_topology = self.state != GroupState.RUNNING
        level = logging.INFO if first_topology else logging.DEBUG
        log.log(
            level,
            "Topology: %d devices, %d connections",
            len(self._incoming_devices),
            len(self._incoming_connections),
        )

        self._update_device_list()
        self._rebuild_topology()

        if first_topology:
            self.state = GroupState.RUNNING

    def on_device_version(self, topology_index: int, version: str) -> None:
        uid = self._uid_from_index(topology_index)
        if dev := self._devices.get(uid):
            dev.version = version

    def on_device_name(self, topology_index: int, name: str) -> None:
        uid = self._uid_from_index(topology_index)
        if dev := self._devices.get(uid):
            dev.name = name

    def on_packet_ack(self, device_index: int, counter: int) -> None:
        uid = self._uid_from_index(device_index)
        if uid:
            self._update_api_ping(uid)
            if (heap := self._heaps.get(uid)) and heap.handle_ack(counter):
                self._flush_heap(uid, heap, time.monotonic())

    def on_firmware_update_ack(self, device_index: int, code: int, detail: int) -> None:
        uid = self._uid_from_index(device_index)
        if uid:
            self._update_api_ping(uid)

    def on_touch(
        self,
        device_index: int,
        timestamp: int,
        touch_index: int,
        x: int,
        y: int,
        z: int,
        vx: int,
        vy: int,
        vz: int,
        is_start: bool,
        is_end: bool,
    ) -> None:
        uid = self._uid_from_index(device_index)
        if uid:
            self._update_api_ping(uid)
            event = TouchEvent.from_raw(
                uid, timestamp, touch_index, x, y, z, vx, vy, vz, is_start, is_end
            )
            for cb in self.on_touch_event:
                cb(event)

    def on_button(self, device_index: int, timestamp: int, button_id: int, is_down: bool) -> None:
        uid = self._uid_from_index(device_index)
        if uid:
            self._update_api_ping(uid)
            event = ButtonEvent(uid=uid, timestamp=timestamp, button_id=button_id, is_down=is_down)
            for cb in self.on_button_event:
                cb(event)

    def on_program_event(
        self, device_index: int, timestamp: int, data: tuple[int, int, int]
    ) -> None:
        pass

    def on_config_update(
        self, device_index: int, item: int, value: int, min_val: int, max_val: int
    ) -> None:
        uid = self._uid_from_index(device_index)
        if uid:
            self._update_api_ping(uid)
            cv = ConfigValue(item=item, value=value, min_val=min_val, max_val=max_val)
            self._config.setdefault(uid, {})[item] = cv
            for cb in self.on_config_changed:
                cb(uid, cv)

    def on_config_set(self, device_index: int, item: int, value: int) -> None:
        uid = self._uid_from_index(device_index)
        if uid:
            self._update_api_ping(uid)
            cv = ConfigValue(item=item, value=value)
            self._config.setdefault(uid, {})[item] = cv
            for cb in self.on_config_changed:
                cb(uid, cv)

    def on_config_factory_sync_end(self, device_index: int) -> None:
        uid = self._uid_from_index(device_index)
        if uid:
            log.debug("Factory sync complete for device %d", uid)

    def on_config_factory_sync_reset(self, device_index: int) -> None:
        uid = self._uid_from_index(device_index)
        if uid:
            self._config.pop(uid, None)
            log.debug("Factory sync reset for device %d", uid)

    def on_log_message(self, device_index: int, message: str) -> None:
        uid = self._uid_from_index(device_index)
        log.debug("Device %d log: %s", uid, message)

    # ── Internal topology update ──────────────────────────────────────────

    def _update_device_list(self) -> None:
        """Merge incoming topology with current device list."""
        incoming_serials = {d.serial for d in self._incoming_devices}

        # Remove devices no longer in topology
        to_remove = [
            uid for uid, dev in self._devices.items() if dev.serial not in incoming_serials
        ]
        for uid in to_remove:
            self._remove_device(uid)

        # Determine master
        if not self.master_uid:
            if self.master_serial:
                self.master_uid = self._uid_from_serial(self.master_serial)
            elif self._incoming_devices:
                first = self._incoming_devices[0]
                self.master_uid = self._uid_from_serial(first.serial)
                self.master_serial = first.serial

        # Add or update devices
        for inc in self._incoming_devices:
            uid = self._uid_from_serial(inc.serial)
            if uid in self._devices:
                dev = self._devices[uid]
                dev.topology_index = inc.topology_index
                dev.battery_level = inc.battery_level
                dev.battery_charging = inc.battery_charging
            else:
                self._devices[uid] = DeviceInfo(
                    uid=uid,
                    topology_index=inc.topology_index,
                    serial=inc.serial,
                    block_type=block_type_from_serial(inc.serial),
                    battery_level=inc.battery_level,
                    battery_charging=inc.battery_charging,
                    is_master=(uid == self.master_uid),
                    master_uid=self.master_uid,
                )


# ── Private data containers ───────────────────────────────────────────────────


@dataclass(frozen=True)
class _IncomingDevice:
    topology_index: int
    serial: str
    battery_level: int
    battery_charging: bool


@dataclass(frozen=True)
class _IncomingConnection:
    dev1_idx: int
    port1: int
    dev2_idx: int
    port2: int
