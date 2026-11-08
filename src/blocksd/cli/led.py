"""LED commands send patterns through the running daemon."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import typer

from blocksd.cli.app import app
from blocksd.cli.client import ClientError, connect
from blocksd.led.bitmap import Color, LEDGrid

if TYPE_CHECKING:
    from collections.abc import Callable

led_app = typer.Typer(name="led", help="Control device LEDs", no_args_is_help=True)
app.add_typer(led_app)


def _run_with_pattern(
    pattern_fn: Callable[[LEDGrid], None],
    verbose: bool = False,  # noqa: ARG001
    *,
    ctx: typer.Context,
    device: str | None = None,
    key_lighting: bool = False,
) -> None:
    """Submit a frame without taking ownership of the MIDI connection."""
    with connect(ctx) as client:
        devices = client.request("discover")["devices"]
        if device is not None:
            devices = [dev for dev in devices if dev["serial"] == device]
        targets = [
            dev
            for dev in devices
            if (dev.get("key_count", 0) if key_lighting else dev["grid_width"] * dev["grid_height"])
        ]
        if not targets:
            raise ClientError("No matching device supports this lighting surface.")
        for dev in targets:
            cols = dev["key_count"] if key_lighting else dev["grid_width"]
            rows = 1 if key_lighting else dev["grid_height"]
            grid = LEDGrid(cols=cols, rows=rows)
            pattern_fn(grid)
            pixels = bytearray()
            for y in range(rows):
                for x in range(cols):
                    color = grid.get_pixel(x, y)
                    pixels.extend((color.r, color.g, color.b))
            result = client.request(
                "key_frame" if key_lighting else "frame",
                uid=dev["uid"],
                pixels=base64.b64encode(pixels).decode(),
            )
            if not result.get("accepted"):
                raise ClientError(f"Lighting request rejected for {dev['serial']}.")
            typer.echo(f"Frame accepted for {dev['serial']}. Visible output is device-dependent.")


# ── Commands ─────────────────────────────────────────────────────────────────


@led_app.command()
def keys(
    ctx: typer.Context,
    device: str | None = typer.Option(None, "--device", help="Device serial number"),
    color: str = typer.Argument("rainbow", help="Hex color or 'rainbow' for all 24 LUMI keys"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Send LUMI key colors through the running daemon, then exit."""
    from blocksd.led.patterns import rainbow as rainbow_pattern

    if color.lower() == "rainbow":
        _run_with_pattern(
            rainbow_pattern, verbose=verbose, ctx=ctx, device=device, key_lighting=True
        )
    else:
        parsed = _parse_color(color)
        _run_with_pattern(
            lambda grid: grid.fill(parsed),
            verbose=verbose,
            ctx=ctx,
            device=device,
            key_lighting=True,
        )


@led_app.command()
def solid(
    ctx: typer.Context,
    device: str | None = typer.Option(None, "--device", help="Device serial number"),
    color: str = typer.Argument(help="Hex color, e.g. '#ff00ff' or 'ff00ff'"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Fill all LEDs with a solid color."""
    from blocksd.led.patterns import solid as solid_pattern

    c = _parse_color(color)
    _run_with_pattern(lambda grid: solid_pattern(grid, c), verbose=verbose, ctx=ctx, device=device)


@led_app.command()
def off(
    ctx: typer.Context,
    device: str | None = typer.Option(None, "--device", help="Device serial number"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Turn off all LEDs."""
    from blocksd.led.patterns import off as off_pattern

    _run_with_pattern(off_pattern, verbose=verbose, ctx=ctx, device=device)


@led_app.command()
def rainbow(
    ctx: typer.Context,
    device: str | None = typer.Option(None, "--device", help="Device serial number"),
    brightness: float = typer.Option(1.0, "--brightness", "-b", min=0.0, max=1.0),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Display a rainbow pattern across the LED grid."""
    from blocksd.led.patterns import rainbow as rainbow_pattern

    _run_with_pattern(
        lambda grid: rainbow_pattern(grid, brightness=brightness),
        verbose=verbose,
        ctx=ctx,
        device=device,
    )


@led_app.command(name="gradient")
def gradient_cmd(
    ctx: typer.Context,
    device: str | None = typer.Option(None, "--device", help="Device serial number"),
    start: str = typer.Argument(help="Start hex color"),
    end: str = typer.Argument(help="End hex color"),
    vertical: bool = typer.Option(False, "--vertical", "-V"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Display a gradient between two colors."""
    from blocksd.led.patterns import gradient as gradient_pattern

    c1 = _parse_color(start)
    c2 = _parse_color(end)
    _run_with_pattern(
        lambda grid: gradient_pattern(grid, c1, c2, vertical=vertical),
        verbose=verbose,
        ctx=ctx,
        device=device,
    )


@led_app.command()
def checkerboard(
    ctx: typer.Context,
    device: str | None = typer.Option(None, "--device", help="Device serial number"),
    color1: str = typer.Argument(help="First hex color"),
    color2: str = typer.Argument(help="Second hex color"),
    size: int = typer.Option(1, "--size", "-s", min=1, max=15),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Display a checkerboard pattern."""
    from blocksd.led.patterns import checkerboard as checker_pattern

    c1 = _parse_color(color1)
    c2 = _parse_color(color2)
    _run_with_pattern(
        lambda grid: checker_pattern(grid, c1, c2, size=size),
        verbose=verbose,
        ctx=ctx,
        device=device,
    )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _parse_color(hex_str: str) -> Color:
    """Parse hex color with user-friendly error."""
    try:
        return Color.from_hex(hex_str)
    except ValueError:
        typer.echo(f"Invalid color: {hex_str!r} (expected '#RRGGBB' or 'RRGGBB')", err=True)
        raise typer.Exit(1) from None
