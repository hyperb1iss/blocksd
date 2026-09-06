"""Per-user macOS LaunchAgent installation."""

from __future__ import annotations

import os
import plistlib
import subprocess
import time
from pathlib import Path

import typer

LABEL = "tech.hyperbliss.blocksd"
_SERVICE_NOT_FOUND = 113
_UNLOAD_TIMEOUT = 35.0


def _launchctl(*args: str, allow_absent: bool = False) -> bool:
    command = ["launchctl", *args]
    result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode == 0:
        return True
    if allow_absent and result.returncode == _SERVICE_NOT_FOUND:
        return False
    detail = result.stderr.strip() or result.stdout.strip()
    raise RuntimeError(f"{' '.join(command)} failed ({result.returncode}): {detail}")


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _unload(target: str) -> None:
    if not _launchctl("print", target, allow_absent=True):
        return
    _launchctl("bootout", target)
    # bootout initiates teardown; launchd can retain the job while it exits.
    deadline = time.monotonic() + _UNLOAD_TIMEOUT
    while _launchctl("print", target, allow_absent=True):
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Timed out waiting for launchd to unload {target}")
        time.sleep(0.05)


def _generate_plist(bin_path: str) -> bytes:
    if not Path(bin_path).is_absolute():
        raise ValueError("LaunchAgent executable path must be absolute")
    logs = Path.home() / "Library" / "Logs" / "blocksd"
    return plistlib.dumps(
        {
            "Label": LABEL,
            "ProgramArguments": [bin_path, "run", "--daemon"],
            "RunAtLoad": True,
            "KeepAlive": {"SuccessfulExit": False},
            "StandardOutPath": str(logs / "stdout.log"),
            "StandardErrorPath": str(logs / "stderr.log"),
        }
    )


def install_agent(bin_path: str, *, enable: bool) -> None:
    """Write the agent and optionally replace its running registration."""
    content = _generate_plist(bin_path)
    path = _plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    (Path.home() / "Library" / "Logs" / "blocksd").mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(0o644)
    typer.echo(f"Installed {path}")
    typer.echo(f"  Executable: {bin_path}")
    if not enable:
        typer.echo("LaunchAgent written; active service state unchanged")
        return
    domain = f"gui/{os.getuid()}"
    target = f"{domain}/{LABEL}"
    _unload(target)
    _launchctl("enable", target)
    _launchctl("bootstrap", domain, str(path))
    _launchctl("kickstart", target)
    typer.echo("LaunchAgent enabled and started (starts on login)")


def uninstall_agent() -> None:
    """Unload the service before removing its definition; keep user logs."""
    target = f"gui/{os.getuid()}/{LABEL}"
    _unload(target)
    path = _plist_path()
    if path.exists():
        path.unlink()
        typer.echo(f"Removed {path}")
