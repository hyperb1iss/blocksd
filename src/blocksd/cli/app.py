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
def status() -> None:
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

    typer.echo(f"Found {len(pairs)} ROLI device(s):")
    for pair in pairs:
        typer.echo(f"  {pair.name} (in={pair.input_port}, out={pair.output_port})")


# Register subcommands
import blocksd.cli.install as _install  # noqa: F401, E402
import blocksd.cli.led as _led  # noqa: F401, E402
