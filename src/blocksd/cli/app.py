"""Main CLI application."""

from pathlib import Path

import typer

app = typer.Typer(
    name="blocksd",
    help="ROLI Blocks device manager for Linux, macOS, and Windows",
    no_args_is_help=True,
)


@app.callback()
def main(
    ctx: typer.Context,
    socket: Path | None = typer.Option(None, "--socket", help="Running daemon Unix socket path"),  # noqa: B008
) -> None:
    """Configure the connection used by device commands."""
    ctx.obj = socket


@app.command()
def run(
    ctx: typer.Context,
    foreground: bool = typer.Option(True, "--foreground/--daemon", "-f/-d"),  # noqa: ARG001
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    config: Path | None = typer.Option(default=None, help="Config file path"),  # noqa: B008
) -> None:
    """Start the blocksd daemon."""
    from blocksd.config.loader import load_config
    from blocksd.daemon import start

    cfg = load_config(config)
    cfg.verbose = cfg.verbose or verbose
    if ctx.obj is not None:
        cfg.api_socket = str(ctx.obj)
    try:
        start(cfg)
    except (ValueError, OSError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command()
def ui(
    ctx: typer.Context,
    no_browser: bool = typer.Option(False, "--no-browser", help="Print the dashboard URL only"),
) -> None:
    """Open the running daemon's dashboard without starting another MIDI session."""
    import webbrowser

    from blocksd.cli.client import ClientError, connect

    with connect(ctx) as client:
        response = client.request("ping")
        url = response.get("web_url")
        if not url:
            raise ClientError(
                "This daemon has no dashboard enabled. Enable web_enabled and restart it."
            )
        typer.echo(url)
        if not no_browser:
            webbrowser.open(url)


@app.command()
def status(
    ctx: typer.Context,
    probe: bool = typer.Option(False, "--probe", "-p", help="Include daemon topology details"),
) -> None:
    """Show connected devices through the running daemon."""
    from rich.console import Console
    from rich.table import Table

    from blocksd.cli.client import connect

    with connect(ctx) as client:
        response = client.request("topology" if probe else "discover")
    devices = response["devices"]
    if not devices:
        typer.echo("blocksd is running. No ROLI Blocks devices are connected.")
        return
    table = Table(title="ROLI Blocks Devices")
    table.add_column("Device", style="cyan")
    table.add_column("Serial")
    table.add_column("Battery", justify="right")
    table.add_column("Firmware")
    for device in devices:
        battery = f"{device['battery_level']}%"
        if device["battery_charging"]:
            battery += " charging"
        table.add_row(
            device["name"], device["serial"], battery, device["firmware_version"] or "unknown"
        )
    Console().print(table)
    if probe:
        typer.echo(f"DNA connections: {len(response['connections'])}")


# Register subcommands
import blocksd.cli.config as _config  # noqa: F401, E402
import blocksd.cli.install as _install  # noqa: F401, E402
import blocksd.cli.led as _led  # noqa: F401, E402
import blocksd.cli.program as _program  # noqa: F401, E402
