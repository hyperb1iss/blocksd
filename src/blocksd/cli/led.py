"""CLI LED commands — apply patterns to connected ROLI Blocks devices."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from typing import TYPE_CHECKING

import typer

from blocksd.cli.app import app
from blocksd.device.registry import (
    bitmap_grid_dimensions,
    key_count_for_block,
    supports_key_led_program,
)
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
    *,
    key_lighting: bool = False,
) -> None:
    """Start a mini-daemon, apply a pattern to each device as it connects."""
    from blocksd.logging import setup_logging
    from blocksd.topology.manager import TopologyManager

    setup_logging(verbose=verbose)

    manager = TopologyManager()
    pending_keys: dict[int, DeviceInfo] = {}

    def on_device(dev: DeviceInfo) -> None:
        if key_lighting:
            if not supports_key_led_program(dev.block_type):
                return
            if not dev.version:
                pending_keys[dev.uid] = dev
                return
            pending_keys.pop(dev.uid, None)
            cols, rows = key_count_for_block(dev.block_type), 1
            write_frame = manager.set_key_led_data
        else:
            cols, rows = bitmap_grid_dimensions(dev.block_type)
            if not cols or not rows:
                return
            write_frame = manager.set_led_data
        grid = LEDGrid(cols=cols, rows=rows)
        pattern_fn(grid)
        if write_frame(dev.uid, grid.heap_data):
            log.info("Applied LED pattern to %s (%s)", dev.block_type, dev.serial)
        elif key_lighting:
            log.warning("Key lighting rejected for %s (firmware %s)", dev.serial, dev.version)

    manager.on_device_added.append(on_device)

    def on_removed(dev: DeviceInfo) -> None:
        pending_keys.pop(dev.uid, None)

    if key_lighting:
        manager.on_device_removed.append(on_removed)

    async def deliver_pending_keys() -> None:
        # Firmware arrives separately from discovery without a readiness event.
        while True:
            for dev in list(pending_keys.values()):
                if dev.version:
                    on_device(dev)
            await asyncio.sleep(0.05)

    async def run() -> None:
        loop = asyncio.get_running_loop()
        stop = asyncio.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)

        task = asyncio.create_task(manager.run(), name="led-manager")
        pending_task = (
            asyncio.create_task(deliver_pending_keys(), name="led-key-readiness")
            if key_lighting
            else None
        )
        typer.echo("Scanning for ROLI devices... (Ctrl+C to stop)")
        try:
            await stop.wait()
        finally:
            task.cancel()
            if pending_task is not None:
                pending_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            if pending_task is not None:
                with contextlib.suppress(asyncio.CancelledError):
                    await pending_task

    asyncio.run(run())


# ── Commands ─────────────────────────────────────────────────────────────────


@led_app.command()
def keys(
    color: str = typer.Argument("rainbow", help="Hex color or 'rainbow' for all 24 LUMI keys"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Light LUMI keys with a color or rainbow. Stop the daemon before running.

    Keep this command running to maintain the lights; press Ctrl+C to stop.
    """
    from blocksd.led.patterns import rainbow as rainbow_pattern

    if color.lower() == "rainbow":
        _run_with_pattern(rainbow_pattern, verbose=verbose, key_lighting=True)
    else:
        parsed = _parse_color(color)
        _run_with_pattern(lambda grid: grid.fill(parsed), verbose=verbose, key_lighting=True)


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
