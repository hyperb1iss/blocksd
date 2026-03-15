"""Tests for RemoteHeap — stateful heap manager with ACK tracking."""

from __future__ import annotations

import pytest

from blocksd.device.models import BlockType
from blocksd.device.registry import heap_size_for_block
from blocksd.led.bitmap import Color, LEDGrid
from blocksd.littlefoot.programs import bitmap_led_program, bitmap_led_program_size
from blocksd.protocol.constants import BitSize, DataChangeCommand
from blocksd.protocol.packing import Packed7BitReader
from blocksd.protocol.remote_heap import (
    _COUNTER_MASK,
    MAX_IN_FLIGHT_BYTES,
    RETRANSMIT_TIMEOUT,
    RemoteHeap,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _decode_packet_index(packet: bytes) -> int:
    """Extract the 16-bit packet index from a SharedDataChange SysEx packet."""
    payload = packet[6:-2]  # strip header(6) + checksum + F7
    reader = Packed7BitReader(payload)
    reader.read_bits(BitSize.MESSAGE_TYPE)  # skip message type
    return reader.read_bits(BitSize.PACKET_INDEX)


def _decode_end_marker(packet: bytes) -> str:
    """Decode only enough of the packet to find its terminating command."""
    payload = packet[6:-2]
    reader = Packed7BitReader(payload)
    reader.read_bits(BitSize.MESSAGE_TYPE)
    reader.read_bits(BitSize.PACKET_INDEX)

    while reader.remaining_bits >= BitSize.DATA_CHANGE_COMMAND:
        cmd = reader.read_bits(BitSize.DATA_CHANGE_COMMAND)
        if cmd == DataChangeCommand.END_OF_PACKET:
            return "end_of_packet"
        if cmd == DataChangeCommand.END_OF_CHANGES:
            return "end_of_changes"
        if cmd == DataChangeCommand.SKIP_BYTES_FEW:
            reader.read_bits(BitSize.BYTE_COUNT_FEW)
        elif cmd == DataChangeCommand.SKIP_BYTES_MANY:
            reader.read_bits(BitSize.BYTE_COUNT_MANY)
        elif cmd == DataChangeCommand.SET_SEQUENCE_OF_BYTES:
            while True:
                reader.read_bits(BitSize.BYTE_VALUE)
                if not reader.read_bits(BitSize.BYTE_SEQUENCE_CONTINUES):
                    break
        elif cmd == DataChangeCommand.SET_FEW_BYTES_WITH_VALUE:
            reader.read_bits(BitSize.BYTE_COUNT_FEW)
            reader.read_bits(BitSize.BYTE_VALUE)
        elif cmd == DataChangeCommand.SET_FEW_BYTES_WITH_LAST_VALUE:
            reader.read_bits(BitSize.BYTE_COUNT_FEW)
        elif cmd == DataChangeCommand.SET_MANY_BYTES_WITH_VALUE:
            reader.read_bits(BitSize.BYTE_COUNT_MANY)
            reader.read_bits(BitSize.BYTE_VALUE)

    raise AssertionError("packet did not contain a terminating data-change command")


# ── Basic State ──────────────────────────────────────────────────────────────


class TestRemoteHeapInit:
    def test_initial_size(self):
        heap = RemoteHeap(100)
        assert heap.size == 100

    def test_initial_target_is_zeroed(self):
        heap = RemoteHeap(10)
        assert heap.target == b"\x00" * 10

    def test_initial_state_is_clean(self):
        heap = RemoteHeap(10)
        assert not heap.is_dirty
        assert heap.in_flight_count == 0
        assert heap.in_flight_bytes == 0

    def test_initial_packet_index(self):
        heap = RemoteHeap(10)
        assert heap.packet_index == 0


class TestSetBytes:
    def test_set_bytes_updates_target(self):
        heap = RemoteHeap(10)
        heap.set_bytes(3, b"\xff\xfe")
        t = heap.target
        assert t[3] == 0xFF
        assert t[4] == 0xFE
        assert t[0] == 0

    def test_set_bytes_marks_dirty(self):
        heap = RemoteHeap(10)
        heap.set_bytes(0, b"\x01")
        assert heap.is_dirty

    def test_set_bytes_past_end_raises(self):
        heap = RemoteHeap(10)
        with pytest.raises(ValueError, match="Write past heap end"):
            heap.set_bytes(8, b"\x00\x00\x00")

    def test_set_bytes_at_boundary(self):
        heap = RemoteHeap(10)
        heap.set_bytes(9, b"\xff")
        assert heap.target[9] == 0xFF

    def test_set_bytes_full_overwrite(self):
        heap = RemoteHeap(4)
        heap.set_bytes(0, b"\x01\x02\x03\x04")
        assert heap.target == b"\x01\x02\x03\x04"


# ── Send Changes ─────────────────────────────────────────────────────────────


class TestSendChanges:
    def test_no_changes_returns_none(self):
        heap = RemoteHeap(10)
        assert heap.send_changes(0, now=0.0) is None

    def test_generates_valid_sysex(self):
        heap = RemoteHeap(10)
        heap.set_bytes(0, b"\xff" * 10)
        packet = heap.send_changes(0, now=0.0)
        assert packet is not None
        assert packet[0] == 0xF0
        assert packet[-1] == 0xF7

    def test_packet_contains_device_index(self):
        heap = RemoteHeap(10)
        heap.set_bytes(0, b"\xff")
        packet = heap.send_changes(5, now=0.0)
        assert packet is not None
        assert packet[5] == 5

    def test_packet_index_increments(self):
        heap = RemoteHeap(20)
        heap.set_bytes(0, b"\xff")
        p0 = heap.send_changes(0, now=0.0)
        assert p0 is not None
        assert _decode_packet_index(p0) == 0

        # ACK so we can send more
        heap.handle_ack(0)
        heap.set_bytes(1, b"\xfe")
        p1 = heap.send_changes(0, now=1.0)
        assert p1 is not None
        assert _decode_packet_index(p1) == 1

    def test_tracks_in_flight(self):
        heap = RemoteHeap(10)
        heap.set_bytes(0, b"\xff")
        packet = heap.send_changes(0, now=0.0)
        assert packet is not None
        assert heap.in_flight_count == 1
        assert heap.in_flight_bytes > 0

    def test_not_dirty_after_send(self):
        heap = RemoteHeap(10)
        heap.set_bytes(0, b"\xff")
        heap.send_changes(0, now=0.0)
        # Optimistic: expected state now matches target
        assert not heap.is_dirty

    def test_blocks_when_in_flight_limit_reached(self):
        # Accumulate multiple in-flight packets until limit is hit
        heap = RemoteHeap(512)
        sent = 0
        for i in range(20):
            heap.set_bytes(0, bytes((i + j) % 256 for j in range(180)))
            p = heap.send_changes(0, now=float(i) * 0.01)
            if p is None:
                break
            sent += 1
        # Should have blocked before sending all 20
        assert sent < 20
        assert heap.in_flight_bytes >= MAX_IN_FLIGHT_BYTES

    def test_optimistic_diffing(self):
        """Second send diffs against tail in-flight result, not confirmed state."""
        heap = RemoteHeap(10)
        # First: set byte 0 to 0xFF
        heap.set_bytes(0, b"\xff")
        heap.send_changes(0, now=0.0)
        # Change byte 1 while byte 0 is still in-flight
        heap.set_bytes(1, b"\xee")
        p2 = heap.send_changes(0, now=0.1)
        # Should generate a packet for byte 1 only (byte 0 already in-flight)
        assert p2 is not None


# ── ACK Handling ─────────────────────────────────────────────────────────────


class TestHandleAck:
    def test_ack_clears_in_flight(self):
        heap = RemoteHeap(10)
        heap.set_bytes(0, b"\xff")
        heap.send_changes(0, now=0.0)
        assert heap.in_flight_count == 1
        assert heap.handle_ack(0)
        assert heap.in_flight_count == 0

    def test_ack_unknown_index_returns_false(self):
        heap = RemoteHeap(10)
        assert not heap.handle_ack(42)

    def test_ack_unknown_index_resets_device_state(self):
        heap = RemoteHeap(20)
        heap.set_bytes(0, b"\x01")
        heap.send_changes(0, now=0.0)
        heap.set_bytes(1, b"\x02")
        heap.send_changes(0, now=0.1)

        assert heap.in_flight_count == 2
        assert not heap.handle_ack(99)
        assert heap.in_flight_count == 0
        assert heap.is_dirty is True

    def test_duplicate_ack_is_ignored(self):
        heap = RemoteHeap(10)
        heap.set_bytes(0, b"\xff")
        heap.send_changes(0, now=0.0)

        assert heap.handle_ack(0)
        assert not heap.handle_ack(0)

    def test_ack_confirms_device_state(self):
        heap = RemoteHeap(10)
        heap.set_bytes(0, b"\xff\xfe")
        heap.send_changes(0, now=0.0)
        heap.handle_ack(0)
        # After ACK, target matches confirmed state — not dirty
        assert not heap.is_dirty

    def test_ack_confirms_all_up_to_index(self):
        """ACK for index N confirms messages 0..N."""
        heap = RemoteHeap(20)
        heap.set_bytes(0, b"\x01")
        heap.send_changes(0, now=0.0)  # index 0
        heap.set_bytes(1, b"\x02")
        heap.send_changes(0, now=0.1)  # index 1
        heap.set_bytes(2, b"\x03")
        heap.send_changes(0, now=0.2)  # index 2

        assert heap.in_flight_count == 3
        # ACK index 1 → confirms 0 and 1
        heap.handle_ack(1)
        assert heap.in_flight_count == 1

    def test_ack_allows_new_sends(self):
        heap = RemoteHeap(512)
        # Fill up in-flight queue
        sent_packet_indexes: list[int] = []
        for i in range(20):
            heap.set_bytes(0, bytes((i + j) % 256 for j in range(180)))
            packet = heap.send_changes(0, now=float(i) * 0.01)
            if packet is None:
                break
            sent_packet_indexes.append(_decode_packet_index(packet))
        assert heap.in_flight_bytes >= MAX_IN_FLIGHT_BYTES
        # Blocked
        heap.set_bytes(0, bytes((0xFE + j) % 256 for j in range(180)))
        assert heap.send_changes(0, now=1.0) is None
        # ACK all — frees space
        heap.handle_ack(sent_packet_indexes[-1])
        assert heap.in_flight_bytes == 0
        p = heap.send_changes(0, now=2.0)
        assert p is not None

    def test_ack_seeds_next_packet_index_when_queue_empty(self):
        heap = RemoteHeap(10)

        assert not heap.handle_ack(41)

        heap.set_bytes(0, b"\xff")
        packet = heap.send_changes(0, now=0.0)
        assert packet is not None
        assert _decode_packet_index(packet) == 42


# ── Retransmission ───────────────────────────────────────────────────────────


class TestRetransmit:
    def test_no_retransmit_when_empty(self):
        heap = RemoteHeap(10)
        assert heap.get_retransmit(now=999.0) is None

    def test_no_retransmit_before_timeout(self):
        heap = RemoteHeap(10)
        heap.set_bytes(0, b"\xff")
        heap.send_changes(0, now=1.0)
        assert heap.get_retransmit(now=1.0 + RETRANSMIT_TIMEOUT - 0.001) is None

    def test_retransmit_after_timeout(self):
        heap = RemoteHeap(10)
        heap.set_bytes(0, b"\xff")
        original = heap.send_changes(0, now=1.0)
        retransmit = heap.get_retransmit(now=1.0 + RETRANSMIT_TIMEOUT)
        assert retransmit is not None
        assert retransmit == original

    def test_retransmit_resets_timer(self):
        heap = RemoteHeap(10)
        heap.set_bytes(0, b"\xff")
        heap.send_changes(0, now=1.0)
        # First retransmit
        heap.get_retransmit(now=1.0 + RETRANSMIT_TIMEOUT)
        # Immediately after: no retransmit (timer was reset)
        assert heap.get_retransmit(now=1.0 + RETRANSMIT_TIMEOUT + 0.001) is None
        # After another timeout: retransmit again
        rt2 = heap.get_retransmit(now=1.0 + 2 * RETRANSMIT_TIMEOUT)
        assert rt2 is not None


# ── Counter Wrapping ─────────────────────────────────────────────────────────


class TestCounterWrapping:
    def test_wraps_at_1023(self):
        heap = RemoteHeap(10)
        heap.handle_ack(_COUNTER_MASK - 1)
        heap.set_bytes(0, b"\xff")
        p = heap.send_changes(0, now=0.0)
        assert p is not None
        assert _decode_packet_index(p) == 1023
        assert heap.packet_index == 0  # wrapped

    def test_ack_after_wrap(self):
        heap = RemoteHeap(10)
        heap.handle_ack(_COUNTER_MASK - 1)
        heap.set_bytes(0, b"\xff")
        heap.send_changes(0, now=0.0)
        assert heap.handle_ack(1023)
        assert heap.in_flight_count == 0


# ── Reset ────────────────────────────────────────────────────────────────────


class TestReset:
    def test_full_reset(self):
        heap = RemoteHeap(10)
        heap.set_bytes(0, b"\xff")
        heap.send_changes(0, now=0.0)
        heap.reset()
        assert heap.target == b"\x00" * 10
        assert heap.in_flight_count == 0
        assert heap.packet_index == 0
        assert not heap.is_dirty

    def test_reset_device_state(self):
        heap = RemoteHeap(10)
        heap.set_bytes(0, b"\xff")
        heap.send_changes(0, now=0.0)
        heap.handle_ack(0)
        # Device state is confirmed — now reset it
        heap.reset_device_state()
        assert heap.in_flight_count == 0
        # Target still has data, device is unknown → dirty
        assert heap.is_dirty

    def test_reset_device_state_preserves_target(self):
        heap = RemoteHeap(10)
        heap.set_bytes(5, b"\xab\xcd")
        heap.reset_device_state()
        assert heap.target[5] == 0xAB
        assert heap.target[6] == 0xCD


# ── Unknown State Behavior ───────────────────────────────────────────────────


class TestUnknownState:
    def test_unknown_bytes_become_zero_in_expected(self):
        """Unknown device bytes appear as 0x00, matching C++ uint16→uint8 truncation."""
        heap = RemoteHeap(4)
        # All unknown, target is zero → expected matches target → not dirty
        assert not heap.is_dirty

    def test_unknown_with_nonzero_target_is_dirty(self):
        heap = RemoteHeap(4)
        heap.set_bytes(0, b"\x01")
        assert heap.is_dirty

    def test_unknown_target_zero_no_diff(self):
        """Target 0x00 vs unknown (→0x00): no diff generated."""
        heap = RemoteHeap(4)
        assert heap.send_changes(0, now=0.0) is None

    def test_sends_all_nonzero_on_first_update(self):
        """First send after setting nonzero target sends everything."""
        heap = RemoteHeap(10)
        heap.set_bytes(0, b"\xff" * 10)
        packet = heap.send_changes(0, now=0.0)
        assert packet is not None


# ── Integration ──────────────────────────────────────────────────────────────


class TestIntegration:
    def test_full_lifecycle(self):
        """set → send → ack → modify → send → ack cycle."""
        heap = RemoteHeap(20)

        # Initial upload
        heap.set_bytes(0, bytes(range(20)))
        p1 = heap.send_changes(0, now=0.0)
        assert p1 is not None
        assert heap.in_flight_count == 1

        # ACK confirms
        heap.handle_ack(0)
        assert heap.in_flight_count == 0
        assert not heap.is_dirty

        # Partial update
        heap.set_bytes(5, b"\xff\xff")
        assert heap.is_dirty
        p2 = heap.send_changes(0, now=1.0)
        assert p2 is not None
        # Should be a smaller packet (only 2 bytes changed)
        assert len(p2) < len(p1)

        heap.handle_ack(1)
        assert not heap.is_dirty

    def test_reconnect_cycle(self):
        """Simulate disconnect → reconnect: reset device, resend everything."""
        heap = RemoteHeap(10)
        heap.set_bytes(0, b"\xaa\xbb\xcc")
        heap.send_changes(0, now=0.0)
        heap.handle_ack(0)

        # Device reconnects — state unknown
        heap.reset_device_state()
        assert heap.is_dirty

        # Resend
        p = heap.send_changes(0, now=1.0)
        assert p is not None

    def test_rapid_updates_coalesce(self):
        """Multiple set_bytes before send_changes → single packet."""
        heap = RemoteHeap(20)
        heap.set_bytes(0, b"\x01")
        heap.set_bytes(5, b"\x02")
        heap.set_bytes(10, b"\x03")
        p = heap.send_changes(0, now=0.0)
        assert p is not None
        assert heap.in_flight_count == 1

    def test_large_led_frame_splits_into_multiple_packets(self):
        """Realistic 15x15 RGB565 data should serialize without overflowing."""
        heap = RemoteHeap(heap_size_for_block(BlockType.LIGHTPAD))

        # Seed the device with the LED program first.
        # With unknown device state, this also zeroes the full heap — may take
        # multiple packets (program bytes + explicit zeros for the rest).
        heap.set_bytes(0, bitmap_led_program())
        now = 0.0
        while heap.is_dirty:
            pkt = heap.send_changes(0, now=now)
            assert pkt is not None
            assert heap.handle_ack(_decode_packet_index(pkt))
            now += 0.01

        grid = LEDGrid()
        for y in range(15):
            for x in range(15):
                grid.set_pixel(
                    x,
                    y,
                    Color(
                        r=(x * 17) & 0xFF,
                        g=(y * 19) & 0xFF,
                        b=((x * 11) + (y * 7)) & 0xFF,
                    ),
                )

        heap.set_bytes(bitmap_led_program_size(), grid.heap_data)

        packets: list[bytes] = []
        now = 1.0
        while heap.is_dirty:
            packet = heap.send_changes(0, now=now)
            assert packet is not None
            packets.append(packet)
            assert len(packet) <= 200
            assert heap.handle_ack(_decode_packet_index(packet))
            now += 0.01
            assert len(packets) < 10

        assert len(packets) > 1
        assert _decode_end_marker(packets[0]) == "end_of_packet"
        assert _decode_end_marker(packets[-1]) == "end_of_changes"
