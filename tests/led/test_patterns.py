"""Tests for built-in LED patterns."""

from __future__ import annotations

from blocksd.led.bitmap import BLACK, BLUE, GREEN, RED, LEDGrid
from blocksd.led.patterns import checkerboard, gradient, off, rainbow, solid


class TestSolid:
    def test_fills_all_pixels(self):
        grid = LEDGrid()
        solid(grid, RED)
        for y in range(grid.rows):
            for x in range(grid.cols):
                assert grid.get_pixel(x, y).r > 0

    def test_overrides_previous(self):
        grid = LEDGrid()
        solid(grid, RED)
        solid(grid, BLUE)
        assert grid.get_pixel(0, 0).r == 0
        assert grid.get_pixel(0, 0).b > 0


class TestOff:
    def test_clears_all(self):
        grid = LEDGrid()
        solid(grid, RED)
        off(grid)
        assert grid.heap_data == bytes(grid.heap_size)


class TestGradient:
    def test_horizontal_endpoints(self):
        grid = LEDGrid()
        gradient(grid, RED, BLUE)
        # First column should be reddish
        start = grid.get_pixel(0, 0)
        assert start.r > start.b
        # Last column should be bluish
        end = grid.get_pixel(14, 0)
        assert end.b > end.r

    def test_vertical_endpoints(self):
        grid = LEDGrid()
        gradient(grid, GREEN, RED, vertical=True)
        # Top row should be greenish
        top = grid.get_pixel(0, 0)
        assert top.g > top.r
        # Bottom row should be reddish
        bottom = grid.get_pixel(0, 14)
        assert bottom.r > bottom.g

    def test_horizontal_columns_uniform(self):
        """Each column should have the same color for all rows."""
        grid = LEDGrid()
        gradient(grid, RED, BLUE)
        for x in range(grid.cols):
            ref = grid.get_pixel(x, 0)
            for y in range(1, grid.rows):
                assert grid.get_pixel(x, y) == ref

    def test_vertical_rows_uniform(self):
        """Each row should have the same color for all columns."""
        grid = LEDGrid()
        gradient(grid, RED, BLUE, vertical=True)
        for y in range(grid.rows):
            ref = grid.get_pixel(0, y)
            for x in range(1, grid.cols):
                assert grid.get_pixel(x, y) == ref


class TestRainbow:
    def test_has_variety(self):
        """Rainbow should produce different colors across columns."""
        grid = LEDGrid()
        rainbow(grid)
        colors = {grid.get_pixel(x, 0) for x in range(grid.cols)}
        assert len(colors) > 5  # Should have many distinct colors

    def test_rows_uniform(self):
        """Each column should have the same color for all rows."""
        grid = LEDGrid()
        rainbow(grid)
        for x in range(grid.cols):
            ref = grid.get_pixel(x, 0)
            for y in range(1, grid.rows):
                assert grid.get_pixel(x, y) == ref

    def test_brightness_zero_is_black(self):
        grid = LEDGrid()
        rainbow(grid, brightness=0.0)
        for x in range(grid.cols):
            assert grid.get_pixel(x, 0) == BLACK


class TestCheckerboard:
    def test_alternating_pattern(self):
        grid = LEDGrid()
        checkerboard(grid, RED, BLUE)
        # (0,0) should be color1 (RED)
        assert grid.get_pixel(0, 0).r > 0
        assert grid.get_pixel(0, 0).b == 0
        # (1,0) should be color2 (BLUE)
        assert grid.get_pixel(1, 0).r == 0
        assert grid.get_pixel(1, 0).b > 0
        # (0,1) should be color2 (BLUE)
        assert grid.get_pixel(0, 1).r == 0
        assert grid.get_pixel(0, 1).b > 0
        # (1,1) should be color1 (RED)
        assert grid.get_pixel(1, 1).r > 0
        assert grid.get_pixel(1, 1).b == 0

    def test_larger_cell_size(self):
        grid = LEDGrid()
        checkerboard(grid, RED, BLUE, size=3)
        # (0,0) and (2,2) should be same color (both in first cell)
        assert grid.get_pixel(0, 0) == grid.get_pixel(2, 2)
        # (0,0) and (3,0) should differ (adjacent cells)
        assert grid.get_pixel(0, 0) != grid.get_pixel(3, 0)
