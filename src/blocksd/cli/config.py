"""Device configuration through the running daemon."""

from __future__ import annotations

import typer

from blocksd.cli.app import app
from blocksd.cli.client import ClientError, connect

config_app = typer.Typer(name="config", help="Read/write device settings", no_args_is_help=True)
app.add_typer(config_app)


@config_app.command(name="get")
def config_get(
    ctx: typer.Context,
    item: int = typer.Argument(help="Config item ID (see blocksd config list)"),
    device: str | None = typer.Option(None, "--device", help="Device serial number"),
) -> None:
    """Read a reported setting without opening another MIDI session."""
    with connect(ctx) as client:
        target = client.select_device(device)
        response = client.request("config_get", uid=target["uid"])
        value = next((v for v in response["values"] if v["item"] == item), None)
        if value is None:
            raise ClientError(f"Setting {item} has not been reported by {target['serial']}.")
        typer.echo(f"{target['serial']} config[{item}] = {value['value']}")


@config_app.command(name="set")
def config_set(
    ctx: typer.Context,
    item: int = typer.Argument(help="Config item ID"),
    value: int = typer.Argument(help="Value to set"),
    device: str | None = typer.Option(None, "--device", help="Device serial number"),
) -> None:
    """Change a setting and wait for the device to report the requested value."""
    with connect(ctx) as client:
        target = client.select_device(device)
        uid = target["uid"]
        client.request("subscribe", events=["config", "device"])
        response = client.request("config_set", uid=uid, item=item, value=value)
        if not response.get("ok"):
            raise ClientError(str(response.get("message", "The device rejected the setting.")))
        typer.echo(f"Waiting for {target['serial']} to confirm setting {item}...")
        event = client.wait_for(
            lambda msg: (
                msg.get("uid") == uid
                and (
                    msg.get("type") == "device_removed"
                    or (
                        msg.get("type") == "config_changed"
                        and msg.get("item") == item
                        and msg.get("value") == value
                    )
                )
            )
        )
        if event["type"] == "device_removed":
            raise ClientError("The device disconnected before confirming the setting.")
        typer.echo(f"Confirmed: {target['serial']} config[{item}] = {value}")


@config_app.command(name="list")
def config_list() -> None:
    """Show known system setting IDs. Availability depends on the device."""
    from rich.console import Console
    from rich.table import Table

    from blocksd.device.config_ids import BlockConfigId

    table = Table(title="Block Configuration Items")
    table.add_column("ID", style="bold", justify="right")
    table.add_column("Name", style="cyan")
    for item in sorted(BlockConfigId, key=lambda x: x.value):
        table.add_row(str(item.value), item.name.lower())
    Console().print(table)
