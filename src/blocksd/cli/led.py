"""CLI LED commands — apply patterns to connected ROLI Blocks devices."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from typing import TYPE_CHECKING

import typer

from blocksd.cli.app import app
from blocksd.led.bitmap import Color, LEDGrid

if TYPE_CHECKING:
    from collections.abc import Callable

    from blocksd.device.models import DeviceInfo

led_app = typer.Typer(name="led", help="Control device LEDs", no_args_is_help=True)
app.add_typer(led_app)

log = logging.getLogger(__name__)


# ── Shared runner ────────────────────────────────────────────────────────────


def _run_with_pattern(
    pattern_fn: Callable[[LEDGrid], None],
    verbose: bool = False,
) -> None:
    """Start a mini-daemon, apply a pattern to each device as it connects."""
    from blocksd.logging import setup_logging
    from blocksd.topology.manager import TopologyManager

    setup_logging(verbose=verbose)

    manager = TopologyManager()

    def on_device(dev: DeviceInfo) -> None:
        grid = LEDGrid()
        pattern_fn(grid)
        if manager.set_led_data(dev.uid, grid.heap_data):
            log.info("Applied LED pattern to %s (%s)", dev.block_type, dev.serial)

    manager.on_device_added.append(on_device)

    async def run() -> None:
        loop = asyncio.get_running_loop()
        stop = asyncio.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)

        task = asyncio.create_task(manager.run(), name="led-manager")
        typer.echo("Scanning for ROLI devices... (Ctrl+C to stop)")
        await stop.wait()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(run())


# ── Commands ─────────────────────────────────────────────────────────────────


@led_app.command()
def solid(
    color: str = typer.Argument(help="Hex color, e.g. '#ff00ff' or 'ff00ff'"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Fill all LEDs with a solid color."""
    from blocksd.led.patterns import solid as solid_pattern

    c = _parse_color(color)
    _run_with_pattern(lambda grid: solid_pattern(grid, c), verbose=verbose)


@led_app.command()
def off(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Turn off all LEDs."""
    from blocksd.led.patterns import off as off_pattern

    _run_with_pattern(off_pattern, verbose=verbose)


@led_app.command()
def rainbow(
    brightness: float = typer.Option(1.0, "--brightness", "-b", min=0.0, max=1.0),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Display a rainbow pattern across the LED grid."""
    from blocksd.led.patterns import rainbow as rainbow_pattern

    _run_with_pattern(
        lambda grid: rainbow_pattern(grid, brightness=brightness),
        verbose=verbose,
    )


@led_app.command(name="gradient")
def gradient_cmd(
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
    )


@led_app.command()
def checkerboard(
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
    )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _parse_color(hex_str: str) -> Color:
    """Parse hex color with user-friendly error."""
    try:
        return Color.from_hex(hex_str)
    except ValueError:
        typer.echo(f"Invalid color: {hex_str!r} (expected '#RRGGBB' or 'RRGGBB')", err=True)
        raise typer.Exit(1) from None
