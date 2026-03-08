"""Tests for 7-bit packing/unpacking — the most critical protocol code."""

from hypothesis import given
from hypothesis import strategies as st

from blocksd.protocol.packing import Packed7BitReader, Packed7BitWriter


class TestPacked7BitRoundTrip:
    """Verify that write→read produces the original value for all bit widths."""

    @given(st.integers(min_value=0, max_value=(1 << 7) - 1))
    def test_7_bit_roundtrip(self, value: int) -> None:
        writer = Packed7BitWriter()
        writer.write_bits(value, 7)
        reader = Packed7BitReader(writer.get_data())
        assert reader.read_bits(7) == value

    @given(st.integers(min_value=0, max_value=(1 << 12) - 1))
    def test_12_bit_roundtrip(self, value: int) -> None:
        """12-bit values span byte boundaries — critical for touch coordinates."""
        writer = Packed7BitWriter()
        writer.write_bits(value, 12)
        reader = Packed7BitReader(writer.get_data())
        assert reader.read_bits(12) == value

    @given(st.integers(min_value=0, max_value=(1 << 32) - 1))
    def test_32_bit_roundtrip(self, value: int) -> None:
        """32-bit values span multiple bytes — used for timestamps and config values."""
        writer = Packed7BitWriter()
        writer.write_bits(value, 32)
        reader = Packed7BitReader(writer.get_data())
        assert reader.read_bits(32) == value

    @given(
        st.integers(min_value=0, max_value=0x7F),
        st.integers(min_value=0, max_value=0x1FF),
        st.integers(min_value=0, max_value=0xFFFFFFFF),
    )
    def test_multi_field_roundtrip(self, a: int, b: int, c: int) -> None:
        """Multiple fields packed sequentially — simulates a real message."""
        writer = Packed7BitWriter()
        writer.write_bits(a, 7)   # MessageType
        writer.write_bits(b, 9)   # DeviceCommand
        writer.write_bits(c, 32)  # Timestamp
        reader = Packed7BitReader(writer.get_data())
        assert reader.read_bits(7) == a
        assert reader.read_bits(9) == b
        assert reader.read_bits(32) == c

    def test_single_bit(self) -> None:
        for v in (0, 1):
            writer = Packed7BitWriter()
            writer.write_bits(v, 1)
            reader = Packed7BitReader(writer.get_data())
            assert reader.read_bits(1) == v

    def test_remaining_bits(self) -> None:
        writer = Packed7BitWriter()
        writer.write_bits(0x55, 7)
        writer.write_bits(0xAA, 8)
        data = writer.get_data()
        reader = Packed7BitReader(data)
        assert reader.remaining_bits == len(data) * 7
        reader.read_bits(7)
        assert reader.remaining_bits == len(data) * 7 - 7


class TestPacked7BitWriter:
    def test_empty_size(self) -> None:
        writer = Packed7BitWriter()
        assert writer.size == 0

    def test_exact_7_bits_one_byte(self) -> None:
        writer = Packed7BitWriter()
        writer.write_bits(0x55, 7)
        assert writer.size == 1

    def test_8_bits_two_bytes(self) -> None:
        writer = Packed7BitWriter()
        writer.write_bits(0xFF, 8)
        assert writer.size == 2

    def test_has_capacity(self) -> None:
        writer = Packed7BitWriter(capacity=4)
        assert writer.has_capacity(7)
        assert not writer.has_capacity(100)
