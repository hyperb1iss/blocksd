"""CLI config commands — read and write device configuration."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from typing import TYPE_CHECKING

import typer

from blocksd.cli.app import app

if TYPE_CHECKING:
    from blocksd.device.models import DeviceInfo

config_app = typer.Typer(name="config", help="Read/write device settings", no_args_is_help=True)
app.add_typer(config_app)

log = logging.getLogger(__name__)


@config_app.command(name="get")
def config_get(
    item: int = typer.Argument(help="Config item ID (see BlockConfigId)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Read a configuration value from connected devices."""
    from rich.console import Console

    from blocksd.logging import setup_logging
    from blocksd.topology.manager import TopologyManager

    setup_logging(verbose=verbose)
    console = Console()
    manager = TopologyManager()
    found: dict[int, int | None] = {}

    def on_device(dev: DeviceInfo) -> None:
        cfg = manager.get_config(dev.uid)
        val = cfg.get(item)
        found[dev.uid] = val.value if val else None

    manager.on_device_added.append(on_device)

    async def run() -> None:
        loop = asyncio.get_running_loop()
        stop = asyncio.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)

        task = asyncio.create_task(manager.run())
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=8.0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(run())

    if not found:
        console.print("[yellow]No devices found.[/yellow]")
        raise typer.Exit(1)

    for uid, value in found.items():
        dev = manager.find_device(uid)
        name = dev.block_type if dev else str(uid)
        if value is not None:
            console.print(f"[cyan]{name}[/cyan] config[{item}] = [bold]{value}[/bold]")
        else:
            console.print(f"[cyan]{name}[/cyan] config[{item}] = [dim]not reported[/dim]")


@config_app.command(name="set")
def config_set(
    item: int = typer.Argument(help="Config item ID"),
    value: int = typer.Argument(help="Value to set"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Write a configuration value to connected devices."""
    from rich.console import Console

    from blocksd.logging import setup_logging
    from blocksd.topology.manager import TopologyManager

    setup_logging(verbose=verbose)
    console = Console()
    manager = TopologyManager()
    results: list[tuple[str, bool]] = []

    def on_device(dev: DeviceInfo) -> None:
        ok = manager.set_config(dev.uid, item, value)
        results.append((str(dev.block_type), ok))

    manager.on_device_added.append(on_device)

    async def run() -> None:
        loop = asyncio.get_running_loop()
        stop = asyncio.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)

        task = asyncio.create_task(manager.run())
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=8.0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(run())

    if not results:
        console.print("[yellow]No devices found.[/yellow]")
        raise typer.Exit(1)

    for name, ok in results:
        if ok:
            console.print(f"[green]✓[/green] [cyan]{name}[/cyan] config[{item}] = {value}")
        else:
            console.print(f"[red]✗[/red] [cyan]{name}[/cyan] failed to set config[{item}]")


@config_app.command(name="list")
def config_list() -> None:
    """Show all known configuration item IDs."""
    from rich.console import Console
    from rich.table import Table

    from blocksd.device.config_ids import BlockConfigId

    console = Console()
    table = Table(title="Block Configuration Items")
    table.add_column("ID", style="bold", justify="right")
    table.add_column("Name", style="cyan")

    for item in sorted(BlockConfigId, key=lambda x: x.value):
        table.add_row(str(item.value), item.name.lower())

    console.print(table)
