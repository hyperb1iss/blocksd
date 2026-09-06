# Installation

blocksd runs on Linux with ALSA MIDI, Python 3.13 or newer, and a systemd user session for service management. The quick installer provides uv and a managed Python when needed.

## Quick Install and Upgrade

Download the release installer, inspect it, and run it as your normal user:

```bash
curl -fsSL https://github.com/hyperb1iss/blocksd/releases/latest/download/install.sh -o install-blocksd.sh
less install-blocksd.sh
bash install-blocksd.sh
```

The installer installs or upgrades the latest PyPI release in an isolated uv tool environment, installs udev rules (using sudo), and enables and restarts the systemd user service. Re-running the same command upgrades an existing installation.

To select a release or skip parts of setup:

```bash
bash install-blocksd.sh --version 0.5.0
bash install-blocksd.sh --no-udev
bash install-blocksd.sh --no-service
bash install-blocksd.sh --no-enable
```

The `--no-enable` option writes and reloads the service file without enabling, starting, or restarting the service. Existing systemd drop-ins are preserved. Run `bash install-blocksd.sh --help` for the complete options.

## From PyPI

With uv already installed:

```bash
uv tool install --python 3.13 blocksd
blocksd install
```

Upgrade the package and restart the service to load the new code:

```bash
uv tool upgrade blocksd
blocksd install
systemctl --user status blocksd
```

A package upgrade alone does not replace the running process. If `blocksd` is not on your PATH, run `uv tool update-shell` and open a new terminal.

## Arch Linux Packaging

The repository contains stable and git PKGBUILDs under `packaging/aur/`. AUR publication is separate from GitHub and PyPI releases; check the package's availability and version before using an AUR helper. Package-managed installations should be upgraded through their package manager.

## From Source

Install the development tools listed in [CONTRIBUTING.md](https://github.com/hyperb1iss/blocksd/blob/main/CONTRIBUTING.md), then build the dashboard before installing the service:

```bash
git clone https://github.com/hyperb1iss/blocksd.git
cd blocksd
just install
just web-build
uv run --locked blocksd install
```

Keep the checkout and its virtual environment at that path while the service uses it. After updating the checkout, sync dependencies, rebuild the dashboard, and rerun `uv run --locked blocksd install` to restart the service.

## What Service Setup Does

The udev file at `/etc/udev/rules.d/99-roli-blocks.rules` grants all local users read/write access to matching ROLI devices (`MODE="0666"`) and adds the `uaccess` tag. Installation requires sudo. Reconnect your devices after installing the rules.

The user service at `~/.config/systemd/user/blocksd.service` starts on login and uses systemd readiness and watchdog notifications. Its sandbox includes `ProtectSystem=strict`, `NoNewPrivileges`, and `PrivateTmp`.

```bash
blocksd install                  # udev + service + enable and restart
blocksd install --no-udev        # skip udev rules
blocksd install --no-enable      # write/reload service without restarting
blocksd install --no-service     # skip the service
```

## Verify

```bash
systemctl --user status blocksd
journalctl --user -u blocksd --no-pager -n 30
blocksd status
```

Open `http://localhost:9010` for the running daemon's dashboard. Do not launch `blocksd ui` alongside the service: that command starts another daemon.

The `status --probe`, `led`, and `config` commands open separate MIDI sessions. Stop the service before using those commands, then restart it afterward.

## Native Dependencies

ALSA runtime support is required. If python-rtmidi needs to compile from source, install a C/C++ toolchain, pkg-config, and ALSA/JACK development headers. For Debian or Ubuntu:

```bash
sudo apt-get install build-essential pkg-config libasound2-dev libjack-jackd2-dev
```

Use the equivalent development packages for your distribution. The installer does not install distribution packages.

## Uninstall

```bash
blocksd uninstall               # service and udev rules
uv tool uninstall blocksd       # Python package (uv installations)
```

User configuration is retained. For a distribution package, remove the package through its package manager.

## Next Steps

- [Quick Start](./quick-start): device discovery and standalone CLI tools
- [LittleFoot status](../architecture/littlefoot): why accepted LED writes do not guarantee visible output
