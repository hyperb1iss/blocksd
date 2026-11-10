"""Load temporary LittleFoot applications through the running daemon."""

from __future__ import annotations

import time
from pathlib import Path  # noqa: TC003 - Typer resolves command annotations at runtime
from typing import TYPE_CHECKING

import typer

from blocksd.cli.app import app
from blocksd.cli.client import ClientError, connect

if TYPE_CHECKING:
    from blocksd.cli.client import DaemonClient

program_app = typer.Typer(
    name="program", help="Load and inspect device programs", no_args_is_help=True
)
app.add_typer(program_app)


def wait_for_program(client: DaemonClient, serial: str, *, lighting: bool = False) -> None:
    """Wait for the available device acknowledgement, never infer visible output."""
    deadline = time.monotonic() + 15
    desired = "ready" if lighting else "uploaded"
    while True:
        status = client.request("program_status", serial=serial)["program"]
        if status["state"] == desired:
            typer.echo(f"{serial}: {status['message']}")
            return
        if status["state"] == "unresponsive" or time.monotonic() >= deadline:
            raise ClientError(
                f"{serial}: {status['message']} Run 'blocksd program status --device {serial}' for the current state."
            )
        time.sleep(0.1)


@program_app.command("load")
def load(
    ctx: typer.Context,
    file: Path = typer.Argument(exists=True, dir_okay=False, readable=True),  # noqa: B008
    device: str | None = typer.Option(None, "--device", help="Device serial number"),
    include: list[Path] | None = typer.Option(  # noqa: B008
        None, "--include", help="Additional LittleFoot include file"
    ),
) -> None:
    """Compile and load a temporary program. This replaces the active program."""
    try:
        source, includes = _read_sources(file, include or [])
    except (OSError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    with connect(ctx) as client:
        target = client.select_device(device)
        client.timeout = 20
        client.request(
            "program_load",
            serial=target["serial"],
            name=file.name,
            source=source,
            includes=includes,
        )
        wait_for_program(client, target["serial"])


def _read_sources(file: Path, extra: list[Path]) -> tuple[str, dict[str, str]]:
    from blocksd.api.programs import MAX_SOURCE_BYTES
    from blocksd.littlefoot.source import collect_file_sources

    source, includes = collect_file_sources(file)
    if sum(path.stat().st_size for path in extra) > MAX_SOURCE_BYTES:
        raise ValueError("Source and includes exceed 256 KiB")
    for path in extra:
        content = path.read_text(encoding="utf-8")
        if path.name == file.name or (path.name in includes and includes[path.name] != content):
            raise ValueError(f"Duplicate source filename: {path.name}")
        includes[path.name] = content
    if (
        len(source.encode()) + sum(len(k.encode()) + len(v.encode()) for k, v in includes.items())
        > MAX_SOURCE_BYTES
    ):
        raise ValueError("Source and includes exceed 256 KiB")
    return source, includes


@program_app.command("status")
def status(
    ctx: typer.Context,
    device: str | None = typer.Option(None, "--device", help="Device serial number"),
) -> None:
    """Report upload and execution acknowledgement separately."""
    with connect(ctx) as client:
        target = client.select_device(device)
        program = client.request("program_status", serial=target["serial"])["program"]
        typer.echo(
            f"{target['serial']}: {program['name'] or 'device program'} ({program['state']})"
        )
        typer.echo(program["message"])


@program_app.command("reset")
def reset(
    ctx: typer.Context,
    device: str | None = typer.Option(None, "--device", help="Device serial number"),
) -> None:
    """Request the device's saved program without a factory reset."""
    with connect(ctx) as client:
        target = client.select_device(device)
        client.request("program_reset", serial=target["serial"])
        typer.echo(f"Saved program requested for {target['serial']}.")
