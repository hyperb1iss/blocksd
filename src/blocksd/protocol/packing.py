"""7-bit packing/unpacking — ported from Packed7BitArrayBuilder/Reader in roli_BitPackingUtilities.h.

All ROLI protocol payloads use 7-bit-safe bytes (bit 7 always 0, MIDI SysEx constraint).
Bits are packed LSB-first across byte boundaries.
"""

from __future__ import annotations


class Packed7BitWriter:
    """Writes arbitrary bit-width values into a 7-bit-per-byte array, LSB-first."""

    def __init__(self, capacity: int = 256) -> None:
        self._data = bytearray(capacity)
        self._bytes_written = 0
        self._bits_in_current_byte = 0

    def write_bits(self, value: int, num_bits: int) -> None:
        """Pack `num_bits` from `value` into the stream, LSB-first."""
        while num_bits > 0:
            bits_available = 7 - self._bits_in_current_byte
            bits_to_write = min(bits_available, num_bits)
            mask = (1 << bits_to_write) - 1

            self._data[self._bytes_written] |= (value & mask) << self._bits_in_current_byte
            value >>= bits_to_write
            num_bits -= bits_to_write
            self._bits_in_current_byte += bits_to_write

            if self._bits_in_current_byte >= 7:
                self._bits_in_current_byte = 0
                self._bytes_written += 1

    def has_capacity(self, bits_needed: int) -> bool:
        """Check if there's room for `bits_needed` more bits (leaving space for checksum + F7)."""
        total_bits = (self._bytes_written + 2) * 7 + self._bits_in_current_byte + bits_needed
        return total_bits <= len(self._data) * 7

    @property
    def size(self) -> int:
        return self._bytes_written + (1 if self._bits_in_current_byte > 0 else 0)

    def get_data(self) -> bytes:
        return bytes(self._data[: self.size])

    def get_state(self) -> tuple[int, int, int]:
        """Save state for rollback."""
        current_byte = self._data[self._bytes_written] if self._bytes_written < len(self._data) else 0
        return (self._bytes_written, self._bits_in_current_byte, current_byte)

    def restore(self, state: tuple[int, int, int]) -> None:
        """Restore a previously saved state."""
        self._bytes_written, self._bits_in_current_byte, current_byte = state
        if self._bytes_written < len(self._data):
            self._data[self._bytes_written] = current_byte


class Packed7BitReader:
    """Reads arbitrary bit-width values from a 7-bit-per-byte array, LSB-first."""

    def __init__(self, data: bytes | bytearray) -> None:
        self._data = data
        self._pos = 0
        self._bit_offset = 0
        self._total_bits = len(data) * 7

    def read_bits(self, num_bits: int) -> int:
        """Read `num_bits` from the stream and return as an unsigned integer."""
        value = 0
        bits_read = 0

        while num_bits > 0:
            if self._pos >= len(self._data):
                break

            bits_available = 7 - self._bit_offset
            bits_to_read = min(bits_available, num_bits)
            mask = (1 << bits_to_read) - 1

            value |= ((self._data[self._pos] >> self._bit_offset) & mask) << bits_read
            bits_read += bits_to_read
            num_bits -= bits_to_read
            self._bit_offset += bits_to_read

            if self._bit_offset >= 7:
                self._bit_offset = 0
                self._pos += 1

        return value

    @property
    def remaining_bits(self) -> int:
        return (len(self._data) - self._pos) * 7 - self._bit_offset
