"""Tests for packet checksum calculation."""

from blocksd.protocol.checksum import calculate_checksum


class TestChecksum:
    def test_empty_payload(self) -> None:
        assert calculate_checksum(b"") == 0

    def test_single_byte(self) -> None:
        result = calculate_checksum(bytes([0x42]))
        # size=1, checksum = (1 + 1*2 + 0x42) & 0xFF = 0x45, & 0x7F = 0x45
        assert result == (1 + (1 * 2 + 0x42)) & 0x7F

    def test_deterministic(self) -> None:
        data = bytes([0x01, 0x02, 0x03])
        assert calculate_checksum(data) == calculate_checksum(data)

    def test_always_7_bit(self) -> None:
        """Checksum must always be <= 0x7F (MIDI safe)."""
        for i in range(256):
            result = calculate_checksum(bytes([i] * 10))
            assert 0 <= result <= 0x7F
