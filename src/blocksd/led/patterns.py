"""Built-in LED patterns — solid, gradient, rainbow, checkerboard.

All patterns operate on an LEDGrid instance, modifying its pixel data
in place. Apply a pattern, then upload the grid's heap_data to the
device via SharedDataChange.
"""

from __future__ import annotations

from blocksd.led.bitmap import Color, LEDGrid


def solid(grid: LEDGrid, color: Color) -> None:
    """Fill the entire grid with a single color."""
    grid.fill(color)


def off(grid: LEDGrid) -> None:
    """Turn off all LEDs."""
    grid.clear()


def gradient(
    grid: LEDGrid,
    start: Color,
    end: Color,
    *,
    vertical: bool = False,
) -> None:
    """Linear gradient across the grid.

    Horizontal by default (left=start, right=end).
    Set vertical=True for top-to-bottom.
    """
    steps = grid.rows if vertical else grid.cols
    for i in range(steps):
        t = i / max(1, steps - 1)
        color = Color(
            r=int(start.r + (end.r - start.r) * t),
            g=int(start.g + (end.g - start.g) * t),
            b=int(start.b + (end.b - start.b) * t),
        )
        if vertical:
            for x in range(grid.cols):
                grid.set_pixel(x, i, color)
        else:
            for y in range(grid.rows):
                grid.set_pixel(i, y, color)


def rainbow(grid: LEDGrid, *, saturation: float = 1.0, brightness: float = 1.0) -> None:
    """Rainbow hue sweep across the grid (left to right)."""
    for x in range(grid.cols):
        hue = x / grid.cols
        r, g, b = _hsv_to_rgb(hue, saturation, brightness)
        color = Color(r=int(r * 255), g=int(g * 255), b=int(b * 255))
        for y in range(grid.rows):
            grid.set_pixel(x, y, color)


def checkerboard(grid: LEDGrid, color1: Color, color2: Color, *, size: int = 1) -> None:
    """Alternating checkerboard pattern with configurable cell size."""
    for y in range(grid.rows):
        for x in range(grid.cols):
            is_even = ((x // size) + (y // size)) % 2 == 0
            grid.set_pixel(x, y, color1 if is_even else color2)


def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[float, float, float]:
    """Convert HSV (0-1 range) to RGB (0-1 range)."""
    if s == 0:
        return v, v, v
    i = int(h * 6)
    f = h * 6 - i
    p = v * (1 - s)
    q = v * (1 - s * f)
    t = v * (1 - s * (1 - f))
    match i % 6:
        case 0:
            return v, t, p
        case 1:
            return q, v, p
        case 2:
            return p, v, t
        case 3:
            return p, q, v
        case 4:
            return t, p, v
        case _:
            return v, p, q
