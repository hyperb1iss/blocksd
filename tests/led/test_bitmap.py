"""Tests for LED bitmap grid and RGB 5:6:5 encoding."""

from __future__ import annotations

import pytest

from blocksd.led.bitmap import (
    BLACK,
    BLUE,
    BYTES_PER_PIXEL,
    GREEN,
    LIGHTPAD_COLS,
    LIGHTPAD_ROWS,
    RED,
    WHITE,
    Color,
    LEDGrid,
)

# ── Color Tests ───────────────────────────────────────────────────────────────


class TestColor:
    def test_rgb565_roundtrip_pure_red(self):
        c = Color(r=255, g=0, b=0)
        b0, b1 = c.to_rgb565()
        decoded = Color.from_rgb565(b0, b1)
        assert decoded.r == 248  # 255 >> 3 << 3 = 248
        assert decoded.g == 0
        assert decoded.b == 0

    def test_rgb565_roundtrip_pure_green(self):
        c = Color(r=0, g=255, b=0)
        b0, b1 = c.to_rgb565()
        decoded = Color.from_rgb565(b0, b1)
        assert decoded.r == 0
        assert decoded.g == 252  # 255 >> 2 << 2 = 252
        assert decoded.b == 0

    def test_rgb565_roundtrip_pure_blue(self):
        c = Color(r=0, g=0, b=255)
        b0, b1 = c.to_rgb565()
        decoded = Color.from_rgb565(b0, b1)
        assert decoded.r == 0
        assert decoded.g == 0
        assert decoded.b == 248  # 255 >> 3 << 3 = 248

    def test_rgb565_roundtrip_white(self):
        c = Color(r=255, g=255, b=255)
        b0, b1 = c.to_rgb565()
        decoded = Color.from_rgb565(b0, b1)
        assert decoded.r == 248
        assert decoded.g == 252
        assert decoded.b == 248

    def test_rgb565_roundtrip_black(self):
        c = Color(r=0, g=0, b=0)
        b0, b1 = c.to_rgb565()
        assert b0 == 0 and b1 == 0
        decoded = Color.from_rgb565(b0, b1)
        assert decoded == c

    def test_rgb565_specific_values(self):
        """Verify bit layout matches ROLI BitmapLEDProgram spec."""
        c = Color(r=0b11111000, g=0b11111100, b=0b11111000)  # max 5:6:5 values
        b0, b1 = c.to_rgb565()
        # byte0: red=0x1F (5 bits) | green_low=0x07 (3 bits) << 5 = 0xFF
        assert b0 == 0xFF
        # byte1: green_high=0x07 (3 bits) | blue=0x1F (5 bits) << 3 = 0xFF
        assert b1 == 0xFF

    def test_rgb565_mixed_color(self):
        c = Color(r=128, g=64, b=32)
        b0, b1 = c.to_rgb565()
        decoded = Color.from_rgb565(b0, b1)
        # Check that encoding preserves within 5:6:5 resolution
        assert abs(decoded.r - c.r) < 8  # 5-bit resolution
        assert abs(decoded.g - c.g) < 4  # 6-bit resolution
        assert abs(decoded.b - c.b) < 8  # 5-bit resolution

    def test_from_hex_with_hash(self):
        c = Color.from_hex("#FF00FF")
        assert c.r == 255
        assert c.g == 0
        assert c.b == 255

    def test_from_hex_without_hash(self):
        c = Color.from_hex("00FF00")
        assert c.r == 0
        assert c.g == 255
        assert c.b == 0

    def test_from_hex_invalid_length(self):
        with pytest.raises(ValueError, match="Expected 6 hex chars"):
            Color.from_hex("#FFF")

    def test_bool_nonzero(self):
        assert bool(Color(255, 0, 0)) is True
        assert bool(Color(0, 1, 0)) is True

    def test_bool_zero(self):
        assert bool(Color(0, 0, 0)) is False
        assert bool(BLACK) is False

    def test_precomputed_constants(self):
        assert Color(255, 0, 0) == RED
        assert Color(0, 255, 0) == GREEN
        assert Color(0, 0, 255) == BLUE
        assert Color(255, 255, 255) == WHITE
        assert Color(0, 0, 0) == BLACK


# ── LEDGrid Tests ─────────────────────────────────────────────────────────────


class TestLEDGrid:
    def test_default_dimensions(self):
        grid = LEDGrid()
        assert grid.cols == LIGHTPAD_COLS
        assert grid.rows == LIGHTPAD_ROWS

    def test_heap_size(self):
        grid = LEDGrid()
        assert grid.heap_size == LIGHTPAD_COLS * LIGHTPAD_ROWS * BYTES_PER_PIXEL
        assert grid.heap_size == 450

    def test_initial_state_is_black(self):
        grid = LEDGrid()
        assert grid.heap_data == bytes(450)
        assert grid.get_pixel(0, 0) == BLACK
        assert grid.get_pixel(7, 7) == BLACK
        assert grid.get_pixel(14, 14) == BLACK

    def test_set_and_get_pixel(self):
        grid = LEDGrid()
        color = Color(255, 0, 0)
        grid.set_pixel(5, 3, color)
        got = grid.get_pixel(5, 3)
        # 5:6:5 quantization
        assert got.r == 248
        assert got.g == 0
        assert got.b == 0

    def test_set_pixel_origin(self):
        grid = LEDGrid()
        grid.set_pixel(0, 0, RED)
        # First 2 bytes should be non-zero
        data = grid.heap_data
        assert data[0] != 0 or data[1] != 0

    def test_set_pixel_last(self):
        grid = LEDGrid()
        grid.set_pixel(14, 14, BLUE)
        data = grid.heap_data
        # Last pixel at offset 224*2 = 448
        assert data[448] != 0 or data[449] != 0

    def test_set_pixel_out_of_bounds_ignored(self):
        grid = LEDGrid()
        grid.set_pixel(-1, 0, RED)
        grid.set_pixel(0, -1, RED)
        grid.set_pixel(15, 0, RED)
        grid.set_pixel(0, 15, RED)
        assert grid.heap_data == bytes(450)

    def test_get_pixel_out_of_bounds_returns_black(self):
        grid = LEDGrid()
        assert grid.get_pixel(-1, 0) == BLACK
        assert grid.get_pixel(15, 15) == BLACK

    def test_fill(self):
        grid = LEDGrid()
        grid.fill(RED)
        # All pixels should be the same red
        for y in range(15):
            for x in range(15):
                pixel = grid.get_pixel(x, y)
                assert pixel.r == 248
                assert pixel.g == 0
                assert pixel.b == 0

    def test_fill_rect(self):
        grid = LEDGrid()
        grid.fill_rect(2, 3, 4, 5, GREEN)
        # Inside rect
        for y in range(3, 8):
            for x in range(2, 6):
                assert grid.get_pixel(x, y).g > 0
        # Outside rect
        assert grid.get_pixel(0, 0) == BLACK
        assert grid.get_pixel(14, 14) == BLACK

    def test_fill_rect_clips(self):
        grid = LEDGrid()
        # Partially outside — should not crash
        grid.fill_rect(-5, -5, 20, 20, WHITE)
        # Corner should be set
        pixel = grid.get_pixel(0, 0)
        assert pixel.r > 0

    def test_clear(self):
        grid = LEDGrid()
        grid.fill(RED)
        grid.clear()
        assert grid.heap_data == bytes(450)

    def test_pixel_independence(self):
        """Setting one pixel doesn't affect adjacent pixels."""
        grid = LEDGrid()
        grid.set_pixel(7, 7, RED)
        assert grid.get_pixel(6, 7) == BLACK
        assert grid.get_pixel(8, 7) == BLACK
        assert grid.get_pixel(7, 6) == BLACK
        assert grid.get_pixel(7, 8) == BLACK

    def test_custom_grid_size(self):
        grid = LEDGrid(cols=5, rows=3)
        assert grid.cols == 5
        assert grid.rows == 3
        assert grid.heap_size == 30
        grid.set_pixel(4, 2, RED)
        assert grid.get_pixel(4, 2).r == 248

    def test_heap_data_is_immutable_copy(self):
        grid = LEDGrid()
        data1 = grid.heap_data
        grid.fill(RED)
        data2 = grid.heap_data
        assert data1 != data2
