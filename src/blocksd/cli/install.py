"""Install/uninstall native user services and Linux device permissions."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import typer

from blocksd.cli.app import app

_UDEV_RULES_DEST = Path("/etc/udev/rules.d/99-roli-blocks.rules")

# ROLI USB vendor 0x2AF4 — all known product IDs
_UDEV_RULES = """\
# ROLI Blocks devices — allow non-root MIDI access
# Installed by: blocksd install

SUBSYSTEM=="usb", ATTR{idVendor}=="2af4", ATTR{idProduct}=="0100", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="2af4", ATTR{idProduct}=="0200", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="2af4", ATTR{idProduct}=="0210", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="2af4", ATTR{idProduct}=="0700", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="2af4", ATTR{idProduct}=="0900", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="2af4", ATTR{idProduct}=="0e00", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="2af4", ATTR{idProduct}=="0f00", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="2af4", ATTR{idProduct}=="1000", MODE="0666", TAG+="uaccess"
"""
_SERVICE_DIR = Path.home() / ".config" / "systemd" / "user"
_SERVICE_PATH = _SERVICE_DIR / "blocksd.service"


def _find_blocksd_bin() -> str:
    """Find the installed blocksd binary path."""
    invoked = Path(sys.argv[0]).absolute()
    candidates = [invoked] if invoked.name == "blocksd" else []
    if path := shutil.which("blocksd"):
        candidates.append(Path(path))
    candidates.append(Path.home() / ".local" / "bin" / "blocksd")
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.absolute())
    raise FileNotFoundError("Cannot locate blocksd executable; add its install directory to PATH")


def _generate_service(bin_path: str) -> str:
    # systemd rejects quotes, backslashes and control characters in executable paths.
    if any(char in bin_path for char in ('"', "'", "\\")) or any(
        ord(char) < 32 or ord(char) == 127 for char in bin_path
    ):
        raise ValueError("systemd cannot use this executable path; install in a simpler directory")
    # Specifiers expand in the executable, but environment variables only expand in arguments.
    escaped = bin_path.replace("%", "%%")
    return textwrap.dedent(f"""\
        [Unit]
        Description=ROLI Blocks Device Manager
        Documentation=https://github.com/hyperb1iss/blocksd
        After=sound.target
        Wants=sound.target

        [Service]
        Type=notify
        ExecStart="{escaped}" run --daemon
        Restart=on-failure
        RestartSec=5
        WatchdogSec=30

        # Security hardening (user-service safe subset)
        NoNewPrivileges=true
        ProtectSystem=strict
        PrivateTmp=true
        ProtectKernelTunables=true
        ProtectControlGroups=true

        [Install]
        WantedBy=default.target
    """)


def _run(cmd: list[str], *, sudo: bool = False, check: bool = True) -> bool:
    """Run a command, optionally with sudo."""
    if sudo:
        cmd = ["sudo", *cmd]
    try:
        result = subprocess.run(cmd, check=check)  # noqa: S603
    except (subprocess.CalledProcessError, OSError) as exc:
        typer.echo(f"Command failed: {' '.join(cmd)}: {exc}", err=True)
        if check:
            raise typer.Exit(1) from exc
        return False
    else:
        return result.returncode == 0


@app.command()
def install(
    no_udev: bool = typer.Option(False, "--no-udev", help="Skip udev rules installation"),
    no_service: bool = typer.Option(False, "--no-service", help="Skip background service setup"),
    no_enable: bool = typer.Option(
        False, "--no-enable", help="Write service without enabling or restarting (Linux reloads)"
    ),
) -> None:
    """Install a Linux systemd service or macOS LaunchAgent."""
    _check_platform()
    try:
        # Resolve before any privileged changes so a missing entrypoint fails early.
        bin_path = _find_blocksd_bin() if not no_service else None
        if sys.platform == "linux" and not no_udev:
            _install_udev()
        if bin_path is not None:
            if sys.platform == "darwin":
                from blocksd.cli.launchd import install_agent

                install_agent(bin_path, enable=not no_enable)
            else:
                _install_service(bin_path, enable=not no_enable)
    except typer.Exit:
        raise
    except (OSError, ValueError, RuntimeError) as exc:
        typer.echo(f"Installation failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo("Installation complete.")


@app.command()
def uninstall() -> None:
    """Remove the native user service and Linux device permissions."""
    _check_platform()
    if sys.platform == "darwin":
        from blocksd.cli.launchd import uninstall_agent

        try:
            uninstall_agent()
        except (OSError, RuntimeError) as exc:
            typer.echo(f"Uninstallation failed: {exc}", err=True)
            raise typer.Exit(1) from exc
        typer.echo("blocksd uninstalled.")
        return
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


def _check_platform() -> None:
    if sys.platform not in {"linux", "darwin"}:
        typer.echo("Service installation supports Linux and macOS only.", err=True)
        raise typer.Exit(1)


def _install_udev() -> None:
    """Install udev rules for ROLI device permissions."""
    import tempfile

    typer.echo("Installing udev rules (requires sudo)...")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".rules", delete=False) as f:
        f.write(_UDEV_RULES)
        tmp = f.name
    try:
        _run(["install", "-m", "0644", tmp, str(_UDEV_RULES_DEST)], sudo=True)
        _run(["udevadm", "control", "--reload-rules"], sudo=True)
        _run(["udevadm", "trigger"], sudo=True)
        typer.echo(f"Installed {_UDEV_RULES_DEST}")
    finally:
        Path(tmp).unlink(missing_ok=True)


def _install_service(bin_path: str, *, enable: bool = True) -> None:
    """Install systemd user service."""
    service_content = _generate_service(bin_path)

    _SERVICE_DIR.mkdir(parents=True, exist_ok=True)
    _SERVICE_PATH.write_text(service_content)
    typer.echo(f"Installed {_SERVICE_PATH}")
    typer.echo(f"  Executable: {bin_path}")

    _run(["systemctl", "--user", "daemon-reload"])

    if enable:
        _run(["systemctl", "--user", "enable", "blocksd"])
        _run(["systemctl", "--user", "restart", "blocksd"])
        typer.echo("Service enabled and restarted (starts on login)")
    else:
        typer.echo("Service installed; enable/start/restart state unchanged")
