"""Install/uninstall blocksd systemd service and udev rules."""

from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import typer

from blocksd.cli.app import app

_UDEV_RULES_SRC = Path(__file__).resolve().parents[3] / "systemd" / "99-roli-blocks.rules"
_UDEV_RULES_DEST = Path("/etc/udev/rules.d/99-roli-blocks.rules")
_SERVICE_DIR = Path.home() / ".config" / "systemd" / "user"
_SERVICE_PATH = _SERVICE_DIR / "blocksd.service"


def _find_blocksd_bin() -> str:
    """Find the installed blocksd binary path."""
    path = shutil.which("blocksd")
    if path:
        return path
    # Fallback: common uv tool install location
    candidate = Path.home() / ".local" / "bin" / "blocksd"
    if candidate.exists():
        return str(candidate)
    return str(candidate)  # best guess


def _generate_service(bin_path: str) -> str:
    return textwrap.dedent(f"""\
        [Unit]
        Description=ROLI Blocks Device Manager
        Documentation=https://github.com/hyperb1iss/blocksd
        After=sound.target
        Wants=sound.target

        [Service]
        Type=notify
        ExecStart={bin_path} run --daemon
        Restart=on-failure
        RestartSec=5
        WatchdogSec=30

        # Security hardening
        NoNewPrivileges=true
        ProtectSystem=strict
        ProtectHome=read-only
        PrivateTmp=true
        ProtectKernelTunables=true
        ProtectControlGroups=true

        # Needs access to ALSA/MIDI
        SupplementaryGroups=audio

        [Install]
        WantedBy=default.target
    """)


def _run(cmd: list[str], *, sudo: bool = False, check: bool = True) -> bool:
    """Run a command, optionally with sudo."""
    if sudo:
        cmd = ["sudo", *cmd]
    try:
        subprocess.run(cmd, check=check)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


@app.command()
def install(
    no_udev: bool = typer.Option(False, "--no-udev", help="Skip udev rules installation"),
    no_service: bool = typer.Option(False, "--no-service", help="Skip systemd service"),
    no_enable: bool = typer.Option(False, "--no-enable", help="Don't enable the service"),
) -> None:
    """Install systemd user service and udev rules."""
    if not no_udev:
        _install_udev()
    if not no_service:
        _install_service(enable=not no_enable)
    typer.echo()
    typer.echo("Done! Start with: systemctl --user start blocksd")


@app.command()
def uninstall() -> None:
    """Remove systemd service and udev rules."""
    _run(["systemctl", "--user", "stop", "blocksd"], check=False)
    _run(["systemctl", "--user", "disable", "blocksd"], check=False)

    if _SERVICE_PATH.exists():
        _SERVICE_PATH.unlink()
        _run(["systemctl", "--user", "daemon-reload"])
        typer.echo(f"Removed {_SERVICE_PATH}")

    if _UDEV_RULES_DEST.exists():
        typer.echo("Removing udev rules (requires sudo)...")
        _run(["rm", str(_UDEV_RULES_DEST)], sudo=True)
        _run(["udevadm", "control", "--reload-rules"], sudo=True)
        _run(["udevadm", "trigger"], sudo=True)
        typer.echo("Removed udev rules")

    typer.echo("blocksd uninstalled.")


def _install_udev() -> None:
    """Install udev rules for ROLI device permissions."""
    if not _UDEV_RULES_SRC.exists():
        typer.echo(f"Warning: udev rules not found at {_UDEV_RULES_SRC}", err=True)
        return

    typer.echo("Installing udev rules (requires sudo)...")
    if _run(["cp", str(_UDEV_RULES_SRC), str(_UDEV_RULES_DEST)], sudo=True):
        _run(["udevadm", "control", "--reload-rules"], sudo=True)
        _run(["udevadm", "trigger"], sudo=True)
        typer.echo(f"Installed {_UDEV_RULES_DEST}")
    else:
        typer.echo("Failed to install udev rules", err=True)


def _install_service(*, enable: bool = True) -> None:
    """Install systemd user service."""
    bin_path = _find_blocksd_bin()
    service_content = _generate_service(bin_path)

    _SERVICE_DIR.mkdir(parents=True, exist_ok=True)
    _SERVICE_PATH.write_text(service_content)
    typer.echo(f"Installed {_SERVICE_PATH}")
    typer.echo(f"  ExecStart={bin_path} run --daemon")

    _run(["systemctl", "--user", "daemon-reload"])

    if enable:
        _run(["systemctl", "--user", "enable", "blocksd"])
        typer.echo("Service enabled (starts on login)")
