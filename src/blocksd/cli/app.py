"""Main CLI application."""

import typer

app = typer.Typer(
    name="blocksd",
    help="ROLI Blocks device manager for Linux",
    no_args_is_help=True,
)


@app.command()
def status() -> None:
    """Show connected devices, battery, and topology."""
    typer.echo("blocksd status — not yet implemented")


@app.command()
def run(
    foreground: bool = typer.Option(True, "--foreground/--daemon", "-f/-d"),
) -> None:
    """Start the blocksd daemon."""
    typer.echo(f"blocksd starting ({'foreground' if foreground else 'daemon'} mode)")
