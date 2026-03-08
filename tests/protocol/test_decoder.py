"""Tests for device→host packet decoder."""

from __future__ import annotations

from dataclasses import dataclass, field

from blocksd.protocol.checksum import calculate_checksum
from blocksd.protocol.constants import (
    PROTOCOL_VERSION,
    ROLI_SYSEX_HEADER,
    BitSize,
    ConfigCommand,
    MessageFromDevice,
)
from blocksd.protocol.decoder import decode_packet
from blocksd.protocol.packing import Packed7BitWriter

# ── Test helper: build a fake device→host SysEx packet ────────────────────────


def _build_device_packet(device_index: int, writer: Packed7BitWriter) -> bytes:
    """Wrap a packed payload in a valid device→host SysEx frame."""
    payload = writer.get_data()
    checksum = calculate_checksum(payload)
    # Bit 6 set on device_index byte = device→host direction
    return ROLI_SYSEX_HEADER + bytes([device_index | 0x40]) + payload + bytes([checksum, 0xF7])


def _make_writer(packet_timestamp: int = 1000) -> Packed7BitWriter:
    """Create a writer pre-loaded with a packet timestamp."""
    w = Packed7BitWriter(512)
    w.write_bits(packet_timestamp, BitSize.PACKET_TIMESTAMP)
    return w


# ── Recording handler ─────────────────────────────────────────────────────────


@dataclass
class RecordingHandler:
    """Captures all decoded callbacks for assertion."""

    calls: list[tuple[str, tuple]] = field(default_factory=list)

    def on_topology_begin(self, num_devices: int, num_connections: int) -> None:
        self.calls.append(("topology_begin", (num_devices, num_connections)))

    def on_topology_extend(self, num_devices: int, num_connections: int) -> None:
        self.calls.append(("topology_extend", (num_devices, num_connections)))

    def on_topology_device(
        self, topology_index: int, serial: str, battery_level: int, battery_charging: bool
    ) -> None:
        self.calls.append(
            (
                "topology_device",
                (topology_index, serial, battery_level, battery_charging),
            )
        )

    def on_topology_connection(self, dev1_idx: int, port1: int, dev2_idx: int, port2: int) -> None:
        self.calls.append(("topology_connection", (dev1_idx, port1, dev2_idx, port2)))

    def on_topology_end(self) -> None:
        self.calls.append(("topology_end", ()))

    def on_device_version(self, topology_index: int, version: str) -> None:
        self.calls.append(("device_version", (topology_index, version)))

    def on_device_name(self, topology_index: int, name: str) -> None:
        self.calls.append(("device_name", (topology_index, name)))

    def on_packet_ack(self, device_index: int, counter: int) -> None:
        self.calls.append(("packet_ack", (device_index, counter)))

    def on_firmware_update_ack(self, device_index: int, code: int, detail: int) -> None:
        self.calls.append(("firmware_update_ack", (device_index, code, detail)))

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
        self.calls.append(
            (
                "touch",
                (device_index, timestamp, touch_index, x, y, z, vx, vy, vz, is_start, is_end),
            )
        )

    def on_button(self, device_index: int, timestamp: int, button_id: int, is_down: bool) -> None:
        self.calls.append(("button", (device_index, timestamp, button_id, is_down)))

    def on_program_event(
        self, device_index: int, timestamp: int, data: tuple[int, int, int]
    ) -> None:
        self.calls.append(("program_event", (device_index, timestamp, data)))

    def on_config_update(
        self, device_index: int, item: int, value: int, min_val: int, max_val: int
    ) -> None:
        self.calls.append(("config_update", (device_index, item, value, min_val, max_val)))

    def on_config_set(self, device_index: int, item: int, value: int) -> None:
        self.calls.append(("config_set", (device_index, item, value)))

    def on_config_factory_sync_end(self, device_index: int) -> None:
        self.calls.append(("config_factory_sync_end", (device_index,)))

    def on_config_factory_sync_reset(self, device_index: int) -> None:
        self.calls.append(("config_factory_sync_reset", (device_index,)))

    def on_log_message(self, device_index: int, message: str) -> None:
        self.calls.append(("log_message", (device_index, message)))


# ── Framing tests ─────────────────────────────────────────────────────────────


class TestPacketValidation:
    def test_rejects_short_packet(self) -> None:
        assert not decode_packet(b"\xf0\x00", RecordingHandler())

    def test_rejects_bad_header(self) -> None:
        assert not decode_packet(b"\xf0\x00\x21\x10\x99\x40\x00\x00\xf7", RecordingHandler())

    def test_rejects_missing_f7(self) -> None:
        w = _make_writer()
        payload = w.get_data()
        checksum = calculate_checksum(payload)
        packet = ROLI_SYSEX_HEADER + bytes([0x40]) + payload + bytes([checksum, 0x00])
        assert not decode_packet(packet, RecordingHandler())

    def test_rejects_bad_checksum(self) -> None:
        w = _make_writer()
        payload = w.get_data()
        packet = ROLI_SYSEX_HEADER + bytes([0x40]) + payload + bytes([0x7F, 0xF7])
        assert not decode_packet(packet, RecordingHandler())

    def test_empty_payload_succeeds(self) -> None:
        """Packet with just a timestamp and no messages is valid."""
        w = _make_writer()
        handler = RecordingHandler()
        assert decode_packet(_build_device_packet(0, w), handler)
        assert handler.calls == []


# ── Topology tests ────────────────────────────────────────────────────────────


def _write_serial(w: Packed7BitWriter, serial: str) -> None:
    """Write a 16-char serial (padded with nulls) into the writer."""
    padded = serial.ljust(16, "\x00")
    for ch in padded:
        w.write_bits(ord(ch), BitSize.SERIAL_CHAR)


class TestTopologyDecoding:
    def test_single_device_topology(self) -> None:
        w = _make_writer()
        # Message type
        w.write_bits(MessageFromDevice.DEVICE_TOPOLOGY, BitSize.MESSAGE_TYPE)
        # Protocol version
        w.write_bits(PROTOCOL_VERSION, BitSize.PROTOCOL_VERSION)
        # 1 device, 0 connections
        w.write_bits(1, BitSize.DEVICE_COUNT)
        w.write_bits(0, BitSize.CONNECTION_COUNT)
        # Device info
        _write_serial(w, "LPB12345678ABCDE")
        w.write_bits(0, BitSize.TOPOLOGY_INDEX)  # topology index
        w.write_bits(20, BitSize.BATTERY_LEVEL)
        w.write_bits(1, BitSize.BATTERY_CHARGING)

        handler = RecordingHandler()
        assert decode_packet(_build_device_packet(0, w), handler)
        assert handler.calls[0] == ("topology_begin", (1, 0))
        assert handler.calls[1][0] == "topology_device"
        _, (topo_idx, serial, batt, charging) = handler.calls[1]
        assert topo_idx == 0
        assert serial.startswith("LPB")
        assert batt == 20
        assert charging is True
        assert handler.calls[2] == ("topology_end", ())

    def test_topology_with_connection(self) -> None:
        w = _make_writer()
        w.write_bits(MessageFromDevice.DEVICE_TOPOLOGY, BitSize.MESSAGE_TYPE)
        w.write_bits(PROTOCOL_VERSION, BitSize.PROTOCOL_VERSION)
        w.write_bits(2, BitSize.DEVICE_COUNT)
        w.write_bits(1, BitSize.CONNECTION_COUNT)
        # Device 0
        _write_serial(w, "LPB0000000000000")
        w.write_bits(0, BitSize.TOPOLOGY_INDEX)
        w.write_bits(31, BitSize.BATTERY_LEVEL)
        w.write_bits(0, BitSize.BATTERY_CHARGING)
        # Device 1
        _write_serial(w, "SBB1111111111111")
        w.write_bits(1, BitSize.TOPOLOGY_INDEX)
        w.write_bits(15, BitSize.BATTERY_LEVEL)
        w.write_bits(1, BitSize.BATTERY_CHARGING)
        # Connection
        w.write_bits(0, BitSize.TOPOLOGY_INDEX)
        w.write_bits(2, BitSize.CONNECTOR_PORT)
        w.write_bits(1, BitSize.TOPOLOGY_INDEX)
        w.write_bits(0, BitSize.CONNECTOR_PORT)

        handler = RecordingHandler()
        assert decode_packet(_build_device_packet(0, w), handler)

        names = [c[0] for c in handler.calls]
        assert names == [
            "topology_begin",
            "topology_device",
            "topology_device",
            "topology_connection",
            "topology_end",
        ]
        assert handler.calls[3] == ("topology_connection", (0, 2, 1, 0))

    def test_topology_end_message(self) -> None:
        w = _make_writer()
        w.write_bits(MessageFromDevice.DEVICE_TOPOLOGY_END, BitSize.MESSAGE_TYPE)
        w.write_bits(PROTOCOL_VERSION, BitSize.PROTOCOL_VERSION)

        handler = RecordingHandler()
        assert decode_packet(_build_device_packet(0, w), handler)
        assert handler.calls == [("topology_end", ())]

    def test_rejects_future_protocol_version(self) -> None:
        w = _make_writer()
        w.write_bits(MessageFromDevice.DEVICE_TOPOLOGY, BitSize.MESSAGE_TYPE)
        w.write_bits(PROTOCOL_VERSION + 99, BitSize.PROTOCOL_VERSION)
        w.write_bits(0, BitSize.DEVICE_COUNT)
        w.write_bits(0, BitSize.CONNECTION_COUNT)

        handler = RecordingHandler()
        assert decode_packet(_build_device_packet(0, w), handler)
        assert handler.calls == []  # topology rejected, but packet still valid


# ── Touch tests ───────────────────────────────────────────────────────────────


class TestTouchDecoding:
    def test_touch_start(self) -> None:
        w = _make_writer(packet_timestamp=5000)
        w.write_bits(MessageFromDevice.TOUCH_START, BitSize.MESSAGE_TYPE)
        w.write_bits(3, BitSize.TIMESTAMP_OFFSET)  # +3ms
        w.write_bits(2, BitSize.TOUCH_INDEX)
        w.write_bits(2048, BitSize.TOUCH_X)
        w.write_bits(1024, BitSize.TOUCH_Y)
        w.write_bits(200, BitSize.TOUCH_Z)

        handler = RecordingHandler()
        assert decode_packet(_build_device_packet(1, w), handler)
        assert len(handler.calls) == 1
        name, args = handler.calls[0]
        assert name == "touch"
        dev, ts, idx, x, y, z, vx, vy, vz, start, end = args
        assert dev == 1
        assert ts == 5003  # 5000 + 3
        assert idx == 2
        assert (x, y, z) == (2048, 1024, 200)
        assert (vx, vy, vz) == (0, 0, 0)
        assert start is True
        assert end is False

    def test_touch_with_velocity(self) -> None:
        w = _make_writer(packet_timestamp=10000)
        w.write_bits(MessageFromDevice.TOUCH_END_WITH_VELOCITY, BitSize.MESSAGE_TYPE)
        w.write_bits(1, BitSize.TIMESTAMP_OFFSET)
        w.write_bits(0, BitSize.TOUCH_INDEX)
        w.write_bits(100, BitSize.TOUCH_X)
        w.write_bits(200, BitSize.TOUCH_Y)
        w.write_bits(50, BitSize.TOUCH_Z)
        w.write_bits(10, BitSize.TOUCH_VX)
        w.write_bits(20, BitSize.TOUCH_VY)
        w.write_bits(30, BitSize.TOUCH_VZ)

        handler = RecordingHandler()
        assert decode_packet(_build_device_packet(0, w), handler)
        _, args = handler.calls[0]
        assert args == (0, 10001, 0, 100, 200, 50, 10, 20, 30, False, True)


# ── Button tests ──────────────────────────────────────────────────────────────


class TestButtonDecoding:
    def test_button_down(self) -> None:
        w = _make_writer(packet_timestamp=7000)
        w.write_bits(MessageFromDevice.CONTROL_BUTTON_DOWN, BitSize.MESSAGE_TYPE)
        w.write_bits(5, BitSize.TIMESTAMP_OFFSET)
        w.write_bits(42, BitSize.CONTROL_BUTTON_ID)

        handler = RecordingHandler()
        assert decode_packet(_build_device_packet(2, w), handler)
        assert handler.calls == [("button", (2, 7005, 42, True))]

    def test_button_up(self) -> None:
        w = _make_writer()
        w.write_bits(MessageFromDevice.CONTROL_BUTTON_UP, BitSize.MESSAGE_TYPE)
        w.write_bits(0, BitSize.TIMESTAMP_OFFSET)
        w.write_bits(99, BitSize.CONTROL_BUTTON_ID)

        handler = RecordingHandler()
        assert decode_packet(_build_device_packet(0, w), handler)
        assert handler.calls[0] == ("button", (0, 1000, 99, False))


# ── ACK tests ─────────────────────────────────────────────────────────────────


class TestACKDecoding:
    def test_packet_ack(self) -> None:
        w = _make_writer()
        w.write_bits(MessageFromDevice.PACKET_ACK, BitSize.MESSAGE_TYPE)
        w.write_bits(512, BitSize.PACKET_COUNTER)

        handler = RecordingHandler()
        assert decode_packet(_build_device_packet(3, w), handler)
        assert handler.calls == [("packet_ack", (3, 512))]

    def test_firmware_update_ack(self) -> None:
        w = _make_writer()
        w.write_bits(MessageFromDevice.FIRMWARE_UPDATE_ACK, BitSize.MESSAGE_TYPE)
        w.write_bits(7, BitSize.FIRMWARE_UPDATE_ACK_CODE)
        w.write_bits(0xDEAD, BitSize.FIRMWARE_UPDATE_ACK_DETAIL)

        handler = RecordingHandler()
        assert decode_packet(_build_device_packet(0, w), handler)
        assert handler.calls == [("firmware_update_ack", (0, 7, 0xDEAD))]


# ── Config tests ──────────────────────────────────────────────────────────────


class TestConfigDecoding:
    def test_config_update(self) -> None:
        w = _make_writer()
        w.write_bits(MessageFromDevice.CONFIG_MESSAGE, BitSize.MESSAGE_TYPE)
        w.write_bits(ConfigCommand.UPDATE_CONFIG, BitSize.CONFIG_COMMAND)
        w.write_bits(10, BitSize.CONFIG_ITEM_INDEX)
        w.write_bits(500, BitSize.CONFIG_ITEM_VALUE)
        w.write_bits(0, BitSize.CONFIG_ITEM_VALUE)  # min
        w.write_bits(1000, BitSize.CONFIG_ITEM_VALUE)  # max

        handler = RecordingHandler()
        assert decode_packet(_build_device_packet(1, w), handler)
        assert handler.calls == [("config_update", (1, 10, 500, 0, 1000))]

    def test_config_set(self) -> None:
        w = _make_writer()
        w.write_bits(MessageFromDevice.CONFIG_MESSAGE, BitSize.MESSAGE_TYPE)
        w.write_bits(ConfigCommand.SET_CONFIG, BitSize.CONFIG_COMMAND)
        w.write_bits(5, BitSize.CONFIG_ITEM_INDEX)
        w.write_bits(42, BitSize.CONFIG_ITEM_VALUE)

        handler = RecordingHandler()
        assert decode_packet(_build_device_packet(0, w), handler)
        assert handler.calls == [("config_set", (0, 5, 42))]

    def test_config_factory_sync_end(self) -> None:
        w = _make_writer()
        w.write_bits(MessageFromDevice.CONFIG_MESSAGE, BitSize.MESSAGE_TYPE)
        w.write_bits(ConfigCommand.FACTORY_SYNC_END, BitSize.CONFIG_COMMAND)

        handler = RecordingHandler()
        assert decode_packet(_build_device_packet(2, w), handler)
        assert handler.calls == [("config_factory_sync_end", (2,))]

    def test_config_factory_sync_reset(self) -> None:
        w = _make_writer()
        w.write_bits(MessageFromDevice.CONFIG_MESSAGE, BitSize.MESSAGE_TYPE)
        w.write_bits(ConfigCommand.FACTORY_SYNC_RESET, BitSize.CONFIG_COMMAND)

        handler = RecordingHandler()
        assert decode_packet(_build_device_packet(0, w), handler)
        assert handler.calls == [("config_factory_sync_reset", (0,))]


# ── Program event tests ──────────────────────────────────────────────────────


class TestProgramEventDecoding:
    def test_program_event(self) -> None:
        w = _make_writer(packet_timestamp=9999)
        w.write_bits(MessageFromDevice.PROGRAM_EVENT_MESSAGE, BitSize.MESSAGE_TYPE)
        w.write_bits(0xAABBCCDD, 32)
        w.write_bits(0x11223344, 32)
        w.write_bits(0x00000001, 32)

        handler = RecordingHandler()
        assert decode_packet(_build_device_packet(0, w), handler)
        assert handler.calls == [("program_event", (0, 9999, (0xAABBCCDD, 0x11223344, 0x00000001)))]


# ── Log message tests ────────────────────────────────────────────────────────


class TestLogDecoding:
    def test_log_message(self) -> None:
        w = _make_writer()
        w.write_bits(MessageFromDevice.LOG_MESSAGE, BitSize.MESSAGE_TYPE)
        for ch in "hello":
            w.write_bits(ord(ch), 7)

        handler = RecordingHandler()
        assert decode_packet(_build_device_packet(0, w), handler)
        assert handler.calls == [("log_message", (0, "hello"))]


# ── Version / Name tests ─────────────────────────────────────────────────────


class TestVersionNameDecoding:
    def test_device_version(self) -> None:
        w = _make_writer()
        w.write_bits(MessageFromDevice.DEVICE_VERSION, BitSize.MESSAGE_TYPE)
        w.write_bits(2, BitSize.TOPOLOGY_INDEX)  # device index 2
        version = "1.4.7"
        w.write_bits(len(version), 7)
        for ch in version:
            w.write_bits(ord(ch), 7)

        handler = RecordingHandler()
        assert decode_packet(_build_device_packet(0, w), handler)
        assert handler.calls == [("device_version", (2, "1.4.7"))]

    def test_device_name(self) -> None:
        w = _make_writer()
        w.write_bits(MessageFromDevice.DEVICE_NAME, BitSize.MESSAGE_TYPE)
        w.write_bits(0, BitSize.TOPOLOGY_INDEX)
        name = "MyBlock"
        w.write_bits(len(name), 7)
        for ch in name:
            w.write_bits(ord(ch), 7)

        handler = RecordingHandler()
        assert decode_packet(_build_device_packet(0, w), handler)
        assert handler.calls == [("device_name", (0, "MyBlock"))]


# ── Multi-message packet test ────────────────────────────────────────────────


class TestMultiMessage:
    def test_ack_then_touch_in_one_packet(self) -> None:
        """Multiple messages in a single packet are decoded sequentially."""
        w = _make_writer(packet_timestamp=2000)

        # ACK
        w.write_bits(MessageFromDevice.PACKET_ACK, BitSize.MESSAGE_TYPE)
        w.write_bits(100, BitSize.PACKET_COUNTER)

        # Touch move
        w.write_bits(MessageFromDevice.TOUCH_MOVE, BitSize.MESSAGE_TYPE)
        w.write_bits(2, BitSize.TIMESTAMP_OFFSET)
        w.write_bits(1, BitSize.TOUCH_INDEX)
        w.write_bits(500, BitSize.TOUCH_X)
        w.write_bits(600, BitSize.TOUCH_Y)
        w.write_bits(128, BitSize.TOUCH_Z)

        handler = RecordingHandler()
        assert decode_packet(_build_device_packet(4, w), handler)
        assert len(handler.calls) == 2
        assert handler.calls[0] == ("packet_ack", (4, 100))
        assert handler.calls[1][0] == "touch"
        _, touch_args = handler.calls[1]
        assert touch_args[:3] == (4, 2002, 1)  # device 4, ts 2000+2, touch idx 1
