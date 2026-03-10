"""Main CLI application."""

from pathlib import Path

import typer

app = typer.Typer(
    name="blocksd",
    help="ROLI Blocks device manager for Linux",
    no_args_is_help=True,
)


@app.command()
def run(
    foreground: bool = typer.Option(True, "--foreground/--daemon", "-f/-d"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    config: Path | None = typer.Option(default=None, help="Config file path"),  # noqa: B008
) -> None:
    """Start the blocksd daemon."""
    from blocksd.config.loader import load_config
    from blocksd.daemon import start

    cfg = load_config(config)
    cfg.verbose = cfg.verbose or verbose
    start(cfg)


@app.command()
def status(
    probe: bool = typer.Option(
        False, "--probe", "-p", help="Connect briefly to get full device info"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Show connected devices, battery, and topology."""
    from blocksd.topology.detector import scan_for_blocks

    try:
        pairs = scan_for_blocks()
    except Exception as exc:
        typer.echo("Error: Could not scan MIDI ports (is python-rtmidi installed?)")
        raise typer.Exit(1) from exc

    if not pairs:
        typer.echo("No ROLI Blocks devices found.")
        raise typer.Exit(0)

    if probe:
        _status_probe(pairs, verbose=verbose)
    else:
        _status_quick(pairs)


def _status_quick(pairs: list) -> None:
    """Quick status from MIDI port scan only."""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title="ROLI Blocks Devices")
    table.add_column("Port Name", style="cyan")
    table.add_column("Input", style="dim")
    table.add_column("Output", style="dim")

    for pair in pairs:
        table.add_row(pair.name, str(pair.input_port), str(pair.output_port))

    console.print(table)
    console.print("\n[dim]Use [bold]--probe[/bold] to connect and get full device info.[/dim]")


def _status_probe(pairs: list, *, verbose: bool = False) -> None:
    """Connect briefly to get full device info (serial, battery, topology)."""
    import asyncio
    import contextlib
    import signal

    from rich.console import Console
    from rich.table import Table

    from blocksd.device.models import DeviceInfo, Topology
    from blocksd.logging import setup_logging
    from blocksd.topology.manager import TopologyManager

    setup_logging(verbose=verbose)
    console = Console()
    manager = TopologyManager()
    devices_seen: dict[int, DeviceInfo] = {}
    topology_seen: Topology | None = None

    def on_device(dev: DeviceInfo) -> None:
        devices_seen[dev.uid] = dev

    def on_topology(topo: Topology) -> None:
        nonlocal topology_seen
        topology_seen = topo

    manager.on_device_added.append(on_device)
    manager.on_topology_changed.append(on_topology)

    async def run() -> None:
        loop = asyncio.get_running_loop()
        stop = asyncio.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)

        task = asyncio.create_task(manager.run())
        console.print("[dim]Probing devices... (Ctrl+C to stop, or wait 8s)[/dim]")

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=8.0)

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(run())

    if not devices_seen:
        console.print("[yellow]No devices responded to probe.[/yellow]")
        return

    table = Table(title="ROLI Blocks Devices")
    table.add_column("Type", style="cyan bold")
    table.add_column("Serial", style="dim")
    table.add_column("Battery", justify="right")
    table.add_column("Master", justify="center")
    table.add_column("Version", style="dim")

    for dev in devices_seen.values():
        charging = " ⚡" if dev.battery_charging else ""
        if dev.battery_level > 50:
            battery_style = "green"
        elif dev.battery_level > 20:
            battery_style = "yellow"
        else:
            battery_style = "red"
        table.add_row(
            str(dev.block_type),
            dev.serial,
            f"[{battery_style}]{dev.battery_level}%{charging}[/{battery_style}]",
            "★" if dev.is_master else "",
            dev.version or "—",
        )

    console.print(table)

    if topology_seen and topology_seen.connections:
        console.print(f"\n[dim]Topology: {len(topology_seen.connections)} connection(s)[/dim]")


# Register subcommands
import blocksd.cli.config as _config  # noqa: F401, E402
import blocksd.cli.install as _install  # noqa: F401, E402
import blocksd.cli.led as _led  # noqa: F401, E402
