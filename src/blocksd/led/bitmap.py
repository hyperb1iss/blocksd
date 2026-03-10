"""BitmapLEDProgram — pixel-level LED control for ROLI Blocks.

Each pixel is encoded as RGB 5:6:5 (16 bits) in the device heap.
Lightpad Block has a 15x15 grid = 225 pixels = 450 bytes.

Byte layout per pixel (little-endian):
  byte0: [G2 G1 G0 R4 R3 R2 R1 R0]  = red_5bit | (green_6bit & 0x07) << 5
  byte1: [B4 B3 B2 B1 B0 G5 G4 G3]  = (green_6bit >> 3) | blue_5bit << 3

This matches the BitmapLEDProgram from roli_BitmapLEDProgram.cpp which reads
these bytes on-device via getHeapBits() and draws with fillPixel().
"""

from __future__ import annotations

from dataclasses import dataclass

# Grid dimensions
LIGHTPAD_COLS = 15
LIGHTPAD_ROWS = 15
BYTES_PER_PIXEL = 2


@dataclass(frozen=True, slots=True)
class Color:
    """8-bit RGB color with RGB 5:6:5 conversion."""

    r: int = 0
    g: int = 0
    b: int = 0

    def to_rgb565(self) -> tuple[int, int]:
        """Encode as two bytes in RGB 5:6:5 format (little-endian).

        Red:   8-bit -> 5-bit (>> 3)
        Green: 8-bit -> 6-bit (>> 2)
        Blue:  8-bit -> 5-bit (>> 3)
        """
        r5 = (self.r >> 3) & 0x1F
        g6 = (self.g >> 2) & 0x3F
        b5 = (self.b >> 3) & 0x1F
        byte0 = r5 | ((g6 & 0x07) << 5)
        byte1 = (g6 >> 3) | (b5 << 3)
        return byte0, byte1

    @classmethod
    def from_rgb565(cls, byte0: int, byte1: int) -> Color:
        """Decode from RGB 5:6:5 little-endian bytes."""
        r5 = byte0 & 0x1F
        g6 = ((byte0 >> 5) & 0x07) | ((byte1 & 0x07) << 3)
        b5 = (byte1 >> 3) & 0x1F
        return cls(r=r5 << 3, g=g6 << 2, b=b5 << 3)

    @classmethod
    def from_hex(cls, hex_str: str) -> Color:
        """Parse '#RRGGBB' or 'RRGGBB' hex string."""
        h = hex_str.lstrip("#")
        if len(h) != 6:
            raise ValueError(f"Expected 6 hex chars, got {len(h)}: {hex_str!r}")
        return cls(r=int(h[0:2], 16), g=int(h[2:4], 16), b=int(h[4:6], 16))

    def __bool__(self) -> bool:
        return self.r != 0 or self.g != 0 or self.b != 0


# Precomputed constants
BLACK = Color(0, 0, 0)
WHITE = Color(255, 255, 255)
RED = Color(255, 0, 0)
GREEN = Color(0, 255, 0)
BLUE = Color(0, 0, 255)


class LEDGrid:
    """15x15 LED grid for Lightpad Block.

    Pixels are stored as RGB 5:6:5 in a flat byte array matching the
    device heap layout used by BitmapLEDProgram. The heap_data property
    returns bytes ready for upload via SharedDataChange.
    """

    def __init__(self, cols: int = LIGHTPAD_COLS, rows: int = LIGHTPAD_ROWS) -> None:
        self.cols = cols
        self.rows = rows
        self._data = bytearray(cols * rows * BYTES_PER_PIXEL)

    def set_pixel(self, x: int, y: int, color: Color) -> None:
        """Set a single pixel. Out-of-bounds coordinates are silently ignored."""
        if not (0 <= x < self.cols and 0 <= y < self.rows):
            return
        offset = (x + y * self.cols) * BYTES_PER_PIXEL
        b0, b1 = color.to_rgb565()
        self._data[offset] = b0
        self._data[offset + 1] = b1

    def get_pixel(self, x: int, y: int) -> Color:
        """Read a single pixel's color."""
        if not (0 <= x < self.cols and 0 <= y < self.rows):
            return BLACK
        offset = (x + y * self.cols) * BYTES_PER_PIXEL
        return Color.from_rgb565(self._data[offset], self._data[offset + 1])

    def fill(self, color: Color) -> None:
        """Fill the entire grid with a single color."""
        b0, b1 = color.to_rgb565()
        for i in range(0, len(self._data), BYTES_PER_PIXEL):
            self._data[i] = b0
            self._data[i + 1] = b1

    def fill_rect(self, x: int, y: int, w: int, h: int, color: Color) -> None:
        """Fill a rectangle. Coordinates are clipped to grid bounds."""
        b0, b1 = color.to_rgb565()
        for py in range(max(0, y), min(y + h, self.rows)):
            for px in range(max(0, x), min(x + w, self.cols)):
                offset = (px + py * self.cols) * BYTES_PER_PIXEL
                self._data[offset] = b0
                self._data[offset + 1] = b1

    def clear(self) -> None:
        """Turn off all LEDs (fill with black)."""
        for i in range(len(self._data)):
            self._data[i] = 0

    @property
    def heap_data(self) -> bytes:
        """Heap byte array for upload via SharedDataChange."""
        return bytes(self._data)

    @property
    def heap_size(self) -> int:
        """Total heap size in bytes (450 for 15x15 Lightpad)."""
        return len(self._data)
