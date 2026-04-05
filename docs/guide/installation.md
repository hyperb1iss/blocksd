# Installation

blocksd requires Python 3.13+ and a Linux system with ALSA MIDI support. Most desktop Linux setups already have everything needed.

## Quick Install

The installer script handles everything: installs blocksd, sets up udev rules, and configures a systemd user service.

```bash
curl -fsSL https://raw.githubusercontent.com/hyperb1iss/blocksd/main/install.sh | bash
```

## From PyPI

```bash
uv tool install blocksd
blocksd install    # sets up systemd service + udev rules
```

Or with pip:

```bash
pip install blocksd
blocksd install
```

## Arch Linux (AUR)

::: code-group

```bash [Stable]
yay -S blocksd
```

```bash [Git (latest)]
yay -S blocksd-git
```

:::

## From Source

```bash
git clone https://github.com/hyperb1iss/blocksd.git
cd blocksd
uv sync
uv run blocksd install
```

## What `blocksd install` Sets Up

The `install` command configures three things:

**udev rules** grant your user access to ROLI USB devices without requiring root. The rule file is installed to `/etc/udev/rules.d/99-roli-blocks.rules` and requires sudo for the initial setup.

**systemd user service** auto-starts blocksd on login with watchdog monitoring. The service file goes to `~/.config/systemd/user/blocksd.service`.

**Security hardening** sandboxes the daemon with `ProtectSystem=strict`, `NoNewPrivileges`, `PrivateTmp`, and other systemd security directives.

```bash
blocksd install                  # full setup (udev + systemd)
blocksd install --no-udev        # skip udev rules
blocksd install --no-enable      # install but don't auto-start
```

## Verifying the Installation

Plug in a ROLI Block device and check that blocksd can see it:

```bash
blocksd status
```

You should see your device's MIDI port listed. For full details including serial number, device type, and battery level:

```bash
blocksd status --probe
```

## Uninstalling

```bash
blocksd uninstall    # removes systemd service and udev rules
```

## Dependencies

blocksd's only system dependency is ALSA development headers, which are needed by python-rtmidi. These are typically already installed on desktop Linux systems.

::: code-group

```bash [Debian / Ubuntu]
sudo apt install libasound2-dev
```

```bash [Fedora]
sudo dnf install alsa-lib-devel
```

```bash [Arch]
sudo pacman -S alsa-lib
```

:::

## Next Steps

- [Quick Start](./quick-start): connect your first device and try LED patterns
