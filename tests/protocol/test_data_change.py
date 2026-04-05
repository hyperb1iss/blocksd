"""Tests for SharedDataChange encoder and heap diff algorithm."""

from __future__ import annotations

import pytest

from blocksd.protocol.constants import BitSize, DataChangeCommand
from blocksd.protocol.data_change import (
    DataChangeEncoder,
    DiffRegion,
    build_data_change_packet,
    compute_diff,
    encode_regions,
)
from blocksd.protocol.packing import Packed7BitReader, Packed7BitWriter

# ── Helper ────────────────────────────────────────────────────────────────────


def decode_commands_from_reader(reader: Packed7BitReader) -> list[tuple]:
    """Decode DataChange commands from a reader for verification."""
    commands: list[tuple] = []

    while reader.remaining_bits >= BitSize.DATA_CHANGE_COMMAND:
        cmd = reader.read_bits(BitSize.DATA_CHANGE_COMMAND)

        if cmd == DataChangeCommand.END_OF_PACKET:
            commands.append(("end_of_packet",))
            break
        if cmd == DataChangeCommand.END_OF_CHANGES:
            commands.append(("end_of_changes",))
            break
        if cmd == DataChangeCommand.SKIP_BYTES_FEW:
            count = reader.read_bits(BitSize.BYTE_COUNT_FEW)
            commands.append(("skip_few", count))
        elif cmd == DataChangeCommand.SKIP_BYTES_MANY:
            count = reader.read_bits(BitSize.BYTE_COUNT_MANY)
            commands.append(("skip_many", count))
        elif cmd == DataChangeCommand.SET_SEQUENCE_OF_BYTES:
            values = []
            while True:
                value = reader.read_bits(BitSize.BYTE_VALUE)
                continues = reader.read_bits(BitSize.BYTE_SEQUENCE_CONTINUES)
                values.append(value)
                if not continues:
                    break
            commands.append(("set_sequence", bytes(values)))
        elif cmd == DataChangeCommand.SET_FEW_BYTES_WITH_VALUE:
            count = reader.read_bits(BitSize.BYTE_COUNT_FEW)
            value = reader.read_bits(BitSize.BYTE_VALUE)
            commands.append(("set_few", count, value))
        elif cmd == DataChangeCommand.SET_FEW_BYTES_WITH_LAST_VALUE:
            count = reader.read_bits(BitSize.BYTE_COUNT_FEW)
            commands.append(("set_few_last", count))
        elif cmd == DataChangeCommand.SET_MANY_BYTES_WITH_VALUE:
            count = reader.read_bits(BitSize.BYTE_COUNT_MANY)
            value = reader.read_bits(BitSize.BYTE_VALUE)
            commands.append(("set_many", count, value))

    return commands


def decode_commands(writer: Packed7BitWriter) -> list[tuple]:
    """Decode DataChange commands from a writer's output for verification."""
    return decode_commands_from_reader(Packed7BitReader(writer.get_data()))


# ── DataChangeEncoder Tests ───────────────────────────────────────────────────


class TestDataChangeEncoder:
    def test_skip_few(self):
        writer = Packed7BitWriter(64)
        enc = DataChangeEncoder(writer)
        enc.skip_bytes(5)
        enc.end()
        cmds = decode_commands(writer)
        assert cmds == [("skip_few", 5), ("end_of_changes",)]

    def test_skip_many(self):
        writer = Packed7BitWriter(64)
        enc = DataChangeEncoder(writer)
        enc.skip_bytes(100)
        enc.end()
        cmds = decode_commands(writer)
        assert cmds == [("skip_many", 100), ("end_of_changes",)]

    def test_skip_splits_large(self):
        """Skips > 255 are split into multiple commands."""
        writer = Packed7BitWriter(64)
        enc = DataChangeEncoder(writer)
        enc.skip_bytes(300)
        enc.end()
        cmds = decode_commands(writer)
        # 300 = 255 + 45; 45 > 15 so still uses skip_many
        assert cmds == [("skip_many", 255), ("skip_many", 45), ("end_of_changes",)]

    def test_skip_exact_boundary(self):
        """Skip of exactly 15 uses skipBytesFew."""
        writer = Packed7BitWriter(64)
        enc = DataChangeEncoder(writer)
        enc.skip_bytes(15)
        enc.end()
        cmds = decode_commands(writer)
        assert cmds == [("skip_few", 15), ("end_of_changes",)]

    def test_skip_16_uses_many(self):
        """Skip of 16 uses skipBytesMany (> 15)."""
        writer = Packed7BitWriter(64)
        enc = DataChangeEncoder(writer)
        enc.skip_bytes(16)
        enc.end()
        cmds = decode_commands(writer)
        assert cmds == [("skip_many", 16), ("end_of_changes",)]

    def test_set_sequence(self):
        writer = Packed7BitWriter(64)
        enc = DataChangeEncoder(writer)
        enc.set_sequence(b"\x01\x02\x03")
        enc.end()
        cmds = decode_commands(writer)
        assert cmds == [("set_sequence", b"\x01\x02\x03"), ("end_of_changes",)]

    def test_set_sequence_empty(self):
        """Empty sequence is a no-op."""
        writer = Packed7BitWriter(64)
        enc = DataChangeEncoder(writer)
        enc.set_sequence(b"")
        enc.end()
        cmds = decode_commands(writer)
        assert cmds == [("end_of_changes",)]

    def test_set_sequence_single_byte(self):
        writer = Packed7BitWriter(64)
        enc = DataChangeEncoder(writer)
        enc.set_sequence(b"\xff")
        enc.end()
        cmds = decode_commands(writer)
        assert cmds == [("set_sequence", b"\xff"), ("end_of_changes",)]

    def test_set_repeated_few(self):
        writer = Packed7BitWriter(64)
        enc = DataChangeEncoder(writer)
        enc.set_repeated(0x42, 5)
        enc.end()
        cmds = decode_commands(writer)
        assert cmds == [("set_few", 5, 0x42), ("end_of_changes",)]

    def test_set_repeated_many(self):
        writer = Packed7BitWriter(64)
        enc = DataChangeEncoder(writer)
        enc.set_repeated(0xAA, 100)
        enc.end()
        cmds = decode_commands(writer)
        assert cmds == [("set_many", 100, 0xAA), ("end_of_changes",)]

    def test_set_repeated_splits_large(self):
        """Repeated > 255 bytes split into multiple commands."""
        writer = Packed7BitWriter(128)
        enc = DataChangeEncoder(writer)
        enc.set_repeated(0x55, 300)
        enc.end()
        cmds = decode_commands(writer)
        # 300 = 255 + 45; 45 > 15 so uses set_many again (not few/last)
        assert cmds == [
            ("set_many", 255, 0x55),
            ("set_many", 45, 0x55),
            ("end_of_changes",),
        ]

    def test_last_value_optimization(self):
        """Second repeated call with same value uses setFewBytesWithLastValue."""
        writer = Packed7BitWriter(64)
        enc = DataChangeEncoder(writer)
        enc.set_repeated(0x42, 3)
        enc.set_repeated(0x42, 5)
        enc.end()
        cmds = decode_commands(writer)
        assert cmds == [
            ("set_few", 3, 0x42),
            ("set_few_last", 5),
            ("end_of_changes",),
        ]

    def test_last_value_from_sequence(self):
        """Last value is tracked across set_sequence calls too."""
        writer = Packed7BitWriter(64)
        enc = DataChangeEncoder(writer)
        enc.set_sequence(b"\x01\x02\x03")
        enc.set_repeated(0x03, 4)
        enc.end()
        cmds = decode_commands(writer)
        assert cmds == [
            ("set_sequence", b"\x01\x02\x03"),
            ("set_few_last", 4),
            ("end_of_changes",),
        ]

    def test_end_of_packet(self):
        writer = Packed7BitWriter(64)
        enc = DataChangeEncoder(writer)
        enc.end(is_last=False)
        cmds = decode_commands(writer)
        assert cmds == [("end_of_packet",)]

    def test_end_of_changes(self):
        writer = Packed7BitWriter(64)
        enc = DataChangeEncoder(writer)
        enc.end(is_last=True)
        cmds = decode_commands(writer)
        assert cmds == [("end_of_changes",)]


# ── Diff Tests ────────────────────────────────────────────────────────────────


class TestComputeDiff:
    def test_identical_heaps(self):
        current = b"\x00" * 100
        target = b"\x00" * 100
        assert compute_diff(current, target) == []

    def test_single_byte_change_middle(self):
        current = b"\x00\x00\x00"
        target = b"\x00\xff\x00"
        regions = compute_diff(current, target)
        assert regions == [
            DiffRegion(is_skip=True, offset=0, count=1),
            DiffRegion(is_skip=False, offset=1, count=1),
        ]

    def test_change_at_start(self):
        current = b"\x00\x00\x00"
        target = b"\xff\x00\x00"
        regions = compute_diff(current, target)
        assert regions == [DiffRegion(is_skip=False, offset=0, count=1)]

    def test_change_at_end(self):
        current = b"\x00\x00\x00"
        target = b"\x00\x00\xff"
        regions = compute_diff(current, target)
        assert regions == [
            DiffRegion(is_skip=True, offset=0, count=2),
            DiffRegion(is_skip=False, offset=2, count=1),
        ]

    def test_multiple_changes(self):
        current = bytes(20)
        target = bytearray(20)
        target[3] = 0xFF
        target[4] = 0xFE
        target[15] = 0xAA
        regions = compute_diff(current, bytes(target))
        # [skip(0,3), set(3,2), skip(5,10), set(15,1), skip(16,4)]
        # Trim: [skip(0,3), set(3,2), skip(5,10), set(15,1)]
        # Coalesce: total = 2+10+1 = 13 < 32 → merge into set(3,13)
        assert regions == [
            DiffRegion(is_skip=True, offset=0, count=3),
            DiffRegion(is_skip=False, offset=3, count=13),
        ]

    def test_coalesce_skips_small_gap(self):
        """Small skip between two set regions gets merged."""
        current = bytes(20)
        target = bytearray(20)
        target[0] = 0xFF
        target[5] = 0xAA
        regions = compute_diff(current, bytes(target))
        # Raw: [set(0,1), skip(1,4), set(5,1), skip(6,14)]
        # Trim: [set(0,1), skip(1,4), set(5,1)]
        # Coalesce: 1+4+1 = 6 < 32 → merge
        assert regions == [DiffRegion(is_skip=False, offset=0, count=6)]

    def test_no_coalesce_large_gap(self):
        """Large skip between set regions is preserved."""
        current = bytes(100)
        target = bytearray(100)
        target[0] = 0xFF
        target[50] = 0xAA
        regions = compute_diff(current, bytes(target))
        # Raw: [set(0,1), skip(1,49), set(50,1), skip(51,49)]
        # Trim: [set(0,1), skip(1,49), set(50,1)]
        # Coalesce: 1+49+1 = 51 >= 32 → no merge
        assert regions == [
            DiffRegion(is_skip=False, offset=0, count=1),
            DiffRegion(is_skip=True, offset=1, count=49),
            DiffRegion(is_skip=False, offset=50, count=1),
        ]

    def test_all_changed(self):
        current = bytes(10)
        target = bytes(range(1, 11))
        regions = compute_diff(current, target)
        assert regions == [DiffRegion(is_skip=False, offset=0, count=10)]

    def test_mismatched_sizes(self):
        with pytest.raises(ValueError, match="Heap sizes differ"):
            compute_diff(b"\x00\x00", b"\x00\x00\x00")


# ── Encode Regions Tests ─────────────────────────────────────────────────────


class TestEncodeRegions:
    def _encode_and_decode(self, current: bytes, target: bytes) -> list[tuple]:
        regions = compute_diff(current, target)
        writer = Packed7BitWriter(512)
        enc = DataChangeEncoder(writer)
        encode_regions(enc, regions, target)
        enc.end()
        return decode_commands(writer)

    def test_single_set_byte(self):
        cmds = self._encode_and_decode(b"\x00", b"\xff")
        # Single changed byte: remaining=1 <= 3, so set_repeated(0xFF, 1)
        assert cmds[0] == ("set_few", 1, 0xFF)
        assert cmds[-1] == ("end_of_changes",)

    def test_run_of_identical_bytes(self):
        current = bytes(10)
        target = b"\xaa" * 10
        cmds = self._encode_and_decode(current, target)
        assert cmds[0] == ("set_few", 10, 0xAA)

    def test_varied_sequence(self):
        current = bytes(5)
        target = bytes([1, 2, 3, 4, 5])
        cmds = self._encode_and_decode(current, target)
        assert cmds[0] == ("set_sequence", bytes([1, 2, 3, 4, 5]))

    def test_mixed_runs_and_sequences(self):
        """Verify run-length encoding within a set region."""
        current = bytes(10)
        # [1, 2, 3, 3, 3, 3, 4, 5, 6, 7] — has a run of 4 x 0x03
        target = bytes([1, 2, 3, 3, 3, 3, 4, 5, 6, 7])
        cmds = self._encode_and_decode(current, target)
        # Expected: set_sequence([1,2]), set_repeated(3, 4), set_sequence([4,5,6,7])
        assert ("set_sequence", b"\x01\x02") in cmds
        assert ("set_few", 4, 0x03) in cmds

    def test_skip_then_set(self):
        current = bytes(10)
        target = bytearray(10)
        target[8] = 0xFF
        target[9] = 0xFE
        cmds = self._encode_and_decode(current, bytes(target))
        # Should have a skip(8) then set bytes
        assert any(c[0] in ("skip_few", "skip_many") for c in cmds)


# ── Build Packet Tests ────────────────────────────────────────────────────────


class TestBuildDataChangePacket:
    def test_no_changes_returns_none(self):
        current = target = b"\x00" * 100
        assert build_data_change_packet(0, 0, current, target) is None

    def test_packet_is_valid_sysex(self):
        current = bytes(50)
        target = bytearray(50)
        target[10] = 0xFF
        packet = build_data_change_packet(0, 1, current, bytes(target))
        assert packet is not None
        # SysEx framing
        assert packet[0] == 0xF0
        assert packet[-1] == 0xF7
        # ROLI header
        assert packet[1:5] == bytes([0x00, 0x21, 0x10, 0x77])
        # Device index
        assert packet[5] == 0x00

    def test_packet_contains_shared_data_change_type(self):
        current = bytes(10)
        target = b"\xff" * 10
        packet = build_data_change_packet(0, 42, current, target)
        assert packet is not None
        # After SysEx header (6 bytes), the payload starts
        # First 7 bits of payload should be SHARED_DATA_CHANGE (0x02)
        reader = Packed7BitReader(packet[6:-2])  # skip header, checksum, F7
        msg_type = reader.read_bits(BitSize.MESSAGE_TYPE)
        assert msg_type == 0x02  # SHARED_DATA_CHANGE

    def test_packet_index_encoded(self):
        current = bytes(10)
        target = b"\xff" * 10
        packet = build_data_change_packet(0, 0x1234, current, target)
        assert packet is not None
        reader = Packed7BitReader(packet[6:-2])
        reader.read_bits(BitSize.MESSAGE_TYPE)  # skip msg type
        pkt_idx = reader.read_bits(BitSize.PACKET_INDEX)
        assert pkt_idx == 0x1234

    def test_device_index_in_header(self):
        current = bytes(10)
        target = b"\xff" * 10
        packet = build_data_change_packet(5, 0, current, target)
        assert packet is not None
        assert packet[5] == 5

    def test_checksum_valid(self):
        from blocksd.protocol.checksum import calculate_checksum

        current = bytes(20)
        target = bytes(range(20))
        packet = build_data_change_packet(0, 0, current, target)
        assert packet is not None
        payload = packet[6:-2]  # between header and checksum+F7
        expected_checksum = calculate_checksum(payload)
        assert packet[-2] == expected_checksum

    def test_roundtrip_small_heap(self):
        """End-to-end: build packet, decode data change commands from payload."""
        current = bytes(8)
        target = bytes([0, 0, 0xFF, 0xFF, 0xFF, 0, 0, 0xAA])
        packet = build_data_change_packet(0, 7, current, target)
        assert packet is not None

        # Decode the SysEx payload (strip header + checksum + F7)
        reader = Packed7BitReader(packet[6:-2])
        msg_type = reader.read_bits(BitSize.MESSAGE_TYPE)
        assert msg_type == 0x02  # SHARED_DATA_CHANGE
        pkt_idx = reader.read_bits(BitSize.PACKET_INDEX)
        assert pkt_idx == 7

        # Decode the data change commands from remaining bits
        cmds = decode_commands_from_reader(reader)
        # Should end with end_of_changes
        assert cmds[-1] == ("end_of_changes",)
        # Should contain skip and set commands
        cmd_types = [c[0] for c in cmds]
        assert any(t.startswith(("skip", "set")) for t in cmd_types)
