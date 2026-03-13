"""Tests for the DeviceGroup state machine — uses a mock MIDI connection."""

from __future__ import annotations

import asyncio

from blocksd.led.bitmap import RED, LEDGrid
from blocksd.protocol.checksum import calculate_checksum
from blocksd.protocol.constants import (
    PROTOCOL_VERSION,
    ROLI_SYSEX_HEADER,
    SERIAL_DUMP_REQUEST,
    SERIAL_DUMP_RESPONSE_HEADER,
    BitSize,
    MessageFromDevice,
)
from blocksd.protocol.packing import Packed7BitWriter
from blocksd.topology.device_group import (
    DeviceGroup,
    GroupState,
)

# ── Mock MIDI connection ──────────────────────────────────────────────────────


class MockMidiConnection:
    """Fake MidiConnection for testing — records sends, allows injecting responses."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self._inbox: list[bytes] = []
        self._closed = False
        self.name = "Mock BLOCK"

    def send(self, data: bytes | bytearray) -> bool:
        if self._closed:
            return False
        self.sent.append(bytes(data))
        return True

    def drain(self) -> list[bytes]:
        msgs = list(self._inbox)
        self._inbox.clear()
        return msgs

    async def recv(self, timeout: float | None = None) -> bytes | None:
        # Always return None in tests — we use inject() + drain()
        await asyncio.sleep(0.001)
        return None

    def inject(self, data: bytes) -> None:
        """Inject a message as if it arrived from the device."""
        self._inbox.append(data)

    def close(self) -> None:
        self._closed = True

    @property
    def is_open(self) -> bool:
        return not self._closed


# ── Test helpers ──────────────────────────────────────────────────────────────


def _build_serial_response(serial: str) -> bytes:
    """Build a fake serial dump response."""
    mac = b"48:B6:20:AA:BB:CC"
    return SERIAL_DUMP_RESPONSE_HEADER + mac + serial.encode("ascii") + bytes([0xF7])


def _build_topology_packet(
    serials: list[str],
    connections: list[tuple[int, int, int, int]] | None = None,
    packet_timestamp: int = 1000,
) -> bytes:
    """Build a fake device→host topology packet."""
    w = Packed7BitWriter(1024)
    w.write_bits(packet_timestamp, BitSize.PACKET_TIMESTAMP)

    # Topology message
    w.write_bits(MessageFromDevice.DEVICE_TOPOLOGY, BitSize.MESSAGE_TYPE)
    w.write_bits(PROTOCOL_VERSION, BitSize.PROTOCOL_VERSION)
    w.write_bits(len(serials), BitSize.DEVICE_COUNT)
    w.write_bits(len(connections or []), BitSize.CONNECTION_COUNT)

    for idx, serial in enumerate(serials):
        padded = serial.ljust(16, "\x00")
        for ch in padded:
            w.write_bits(ord(ch), BitSize.SERIAL_CHAR)
        w.write_bits(idx, BitSize.TOPOLOGY_INDEX)
        w.write_bits(20, BitSize.BATTERY_LEVEL)
        w.write_bits(0, BitSize.BATTERY_CHARGING)

    for d1, p1, d2, p2 in connections or []:
        w.write_bits(d1, BitSize.TOPOLOGY_INDEX)
        w.write_bits(p1, BitSize.CONNECTOR_PORT)
        w.write_bits(d2, BitSize.TOPOLOGY_INDEX)
        w.write_bits(p2, BitSize.CONNECTOR_PORT)

    payload = w.get_data()
    checksum = calculate_checksum(payload)
    return ROLI_SYSEX_HEADER + bytes([0x40]) + payload + bytes([checksum, 0xF7])


def _build_ack_packet(device_index: int, counter: int = 1) -> bytes:
    """Build a fake packet ACK."""
    w = Packed7BitWriter(64)
    w.write_bits(0, BitSize.PACKET_TIMESTAMP)
    w.write_bits(MessageFromDevice.PACKET_ACK, BitSize.MESSAGE_TYPE)
    w.write_bits(counter, BitSize.PACKET_COUNTER)

    payload = w.get_data()
    checksum = calculate_checksum(payload)
    return ROLI_SYSEX_HEADER + bytes([device_index | 0x40]) + payload + bytes([checksum, 0xF7])


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestDeviceGroupInit:
    def test_starts_in_requesting_serial_state(self) -> None:
        conn = MockMidiConnection()
        group = DeviceGroup(conn)  # type: ignore[arg-type]
        assert group.state == GroupState.REQUESTING_SERIAL

    def test_sends_serial_request_on_run(self) -> None:
        conn = MockMidiConnection()
        group = DeviceGroup(conn)  # type: ignore[arg-type]

        # Run one tick manually
        group._serial_start_time = __import__("time").monotonic()
        group._send_serial_request()

        assert any(msg == SERIAL_DUMP_REQUEST for msg in conn.sent)


class TestSerialHandling:
    def test_serial_response_updates_master(self) -> None:
        conn = MockMidiConnection()
        group = DeviceGroup(conn)  # type: ignore[arg-type]
        group.state = GroupState.REQUESTING_SERIAL

        response = _build_serial_response("LPB12345678ABCDE")
        group._process_message(response)

        assert group.master_serial == "LPB12345678ABCDE"
        assert group.state == GroupState.REQUESTING_TOPOLOGY


class TestTopologyHandling:
    def test_topology_creates_devices(self) -> None:
        conn = MockMidiConnection()
        group = DeviceGroup(conn)  # type: ignore[arg-type]
        group.state = GroupState.REQUESTING_TOPOLOGY

        topology_pkt = _build_topology_packet(["LPB0000000000000"])
        group._process_message(topology_pkt)

        assert len(group._devices) == 1
        dev = next(iter(group._devices.values()))
        assert dev.serial.startswith("LPB")
        assert group.state == GroupState.RUNNING

    def test_topology_with_two_devices(self) -> None:
        conn = MockMidiConnection()
        group = DeviceGroup(conn)  # type: ignore[arg-type]
        group.state = GroupState.REQUESTING_TOPOLOGY

        topology_pkt = _build_topology_packet(
            ["LPB0000000000000", "SBB1111111111111"],
            connections=[(0, 2, 1, 0)],
        )
        group._process_message(topology_pkt)

        assert len(group._devices) == 2
        assert len(group.topology.connections) == 1

    def test_topology_sets_master_from_first_device(self) -> None:
        conn = MockMidiConnection()
        group = DeviceGroup(conn)  # type: ignore[arg-type]
        group.state = GroupState.REQUESTING_TOPOLOGY

        topology_pkt = _build_topology_packet(["LPB0000000000000"])
        group._process_message(topology_pkt)

        assert group.master_serial == "LPB0000000000000"
        dev = next(iter(group._devices.values()))
        assert dev.is_master


class TestACKHandling:
    def test_ack_creates_ping_entry(self) -> None:
        conn = MockMidiConnection()
        group = DeviceGroup(conn)  # type: ignore[arg-type]
        group.state = GroupState.REQUESTING_TOPOLOGY

        # Set up topology first
        topology_pkt = _build_topology_packet(["LPB0000000000000"])
        group._process_message(topology_pkt)

        # Inject an ACK for device index 0
        ack_pkt = _build_ack_packet(0, counter=1)
        group._process_message(ack_pkt)

        assert len(group._pings) == 1

    def test_device_added_callback_on_first_ack(self) -> None:
        conn = MockMidiConnection()
        group = DeviceGroup(conn)  # type: ignore[arg-type]
        group.state = GroupState.REQUESTING_TOPOLOGY

        added: list[object] = []
        group.on_device_added = [lambda dev: added.append(dev)]

        topology_pkt = _build_topology_packet(["LPB0000000000000"])
        group._process_message(topology_pkt)

        ack_pkt = _build_ack_packet(0)
        group._process_message(ack_pkt)

        assert len(added) == 1

    def test_set_led_data_flushes_immediately(self) -> None:
        conn = MockMidiConnection()
        group = DeviceGroup(conn)  # type: ignore[arg-type]
        group.state = GroupState.REQUESTING_TOPOLOGY

        topology_pkt = _build_topology_packet(["LPB0000000000000"])
        group._process_message(topology_pkt)

        ack_pkt = _build_ack_packet(0)
        group._process_message(ack_pkt)

        grid = LEDGrid()
        grid.fill(RED)

        conn.sent.clear()
        assert group.set_led_data(next(iter(group._devices)), grid.heap_data)
        assert conn.sent, "expected LED data write to be sent immediately"


class TestAPIActivation:
    def test_sends_api_mode_commands_for_unconnected(self) -> None:
        conn = MockMidiConnection()
        group = DeviceGroup(conn)  # type: ignore[arg-type]
        group.state = GroupState.REQUESTING_TOPOLOGY

        topology_pkt = _build_topology_packet(["LPB0000000000000"])
        group._process_message(topology_pkt)

        conn.sent.clear()
        group._start_api_on_unconnected()

        # Should have sent endAPIMode + beginAPIMode
        assert len(conn.sent) == 2
