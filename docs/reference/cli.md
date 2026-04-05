# CLI Commands

blocksd ships a Typer-based CLI for running the daemon, controlling LEDs, managing device configuration, and setting up system integration.

## `blocksd run`

Start the daemon in the foreground.

```bash
blocksd run                  # start with defaults
blocksd run -v               # verbose logging (protocol-level debug output)
blocksd run --config my.toml # explicit config file
```

The daemon scans for ROLI devices, activates API mode, and maintains keepalive pings. It runs until interrupted with Ctrl+C or a SIGTERM signal.

When running under systemd, the daemon sends `READY=1` via sd_notify and periodic watchdog heartbeats.

| Flag                      | Short     | Description                      |
| ------------------------- | --------- | -------------------------------- |
| `--verbose`               | `-v`      | Enable debug logging             |
| `--foreground / --daemon` | `-f / -d` | Run mode (foreground is default) |
| `--config`                |           | Path to TOML config file         |

## `blocksd ui`

Start the daemon with the web dashboard and open a browser.

```bash
blocksd ui                       # default: localhost:9010
blocksd ui --port 8080           # custom port
blocksd ui --host 0.0.0.0       # bind to all interfaces
blocksd ui --no-browser          # start server without opening browser
```

| Flag           | Short | Description                         |
| -------------- | ----- | ----------------------------------- |
| `--port`       | `-p`  | HTTP/WebSocket port (default: 9010) |
| `--host`       |       | Bind address (default: 127.0.0.1)   |
| `--no-browser` |       | Don't auto-open browser             |
| `--verbose`    | `-v`  | Enable debug logging                |
| `--config`     |       | Path to TOML config file            |

## `blocksd status`

Scan for connected ROLI devices.

```bash
blocksd status               # quick scan (MIDI port names only)
blocksd status --probe       # full probe (connects, reads serial/battery/topology)
```

The quick scan lists MIDI ports matching ROLI's naming convention. The `--probe` flag temporarily connects to each device for about 8 seconds to retrieve serial number, device type, firmware version, and battery level, then disconnects.

| Flag        | Short | Description                             |
| ----------- | ----- | --------------------------------------- |
| `--probe`   | `-p`  | Connect briefly to get full device info |
| `--verbose` | `-v`  | Enable debug logging                    |

## `blocksd led`

Control the 15x15 LED grid on Lightpad Block and Lightpad Block M. These commands connect to the running daemon via the Unix socket API, so the daemon must be running first.

### `blocksd led solid`

Fill the entire grid with a single color.

```bash
blocksd led solid '#ff00ff'          # hex color (quote the hash for shell)
blocksd led solid ff00ff             # hash is optional
```

### `blocksd led rainbow`

Sweep a rainbow gradient across the grid.

```bash
blocksd led rainbow
blocksd led rainbow --brightness 128 # dimmer rainbow (0-255)
```

### `blocksd led gradient`

Draw a two-color gradient.

```bash
blocksd led gradient ff0000 0000ff               # horizontal (left → right)
blocksd led gradient ff0000 0000ff --vertical    # vertical (top → bottom)
```

### `blocksd led checkerboard`

Draw a checkerboard pattern.

```bash
blocksd led checkerboard ff0000 00ff00             # 2x2 squares (default)
blocksd led checkerboard ff0000 00ff00 --size 3    # 3x3 squares
blocksd led checkerboard ff0000 00ff00 --size 5    # 5x5 squares
```

### `blocksd led off`

Turn off all LEDs (fill with black).

```bash
blocksd led off
```

## `blocksd config`

Read and write device configuration values. Connects to the running daemon.

### `blocksd config list`

Show all known configuration item IDs and their descriptions.

```bash
blocksd config list
```

### `blocksd config get <id>`

Read a configuration value from the device.

```bash
blocksd config get 10            # read velocity sensitivity
```

### `blocksd config set <id> <value>`

Write a configuration value to the device.

```bash
blocksd config set 10 50         # set velocity sensitivity to 50
```

## `blocksd install`

Set up systemd service and udev rules. The udev rule installation requires sudo.

```bash
blocksd install                  # full setup (udev + systemd + auto-start)
blocksd install --no-udev        # skip udev rules
blocksd install --no-enable      # install service but don't enable on boot
blocksd install --no-service     # skip systemd service entirely
```

This creates:

| File                                     | Purpose                              |
| ---------------------------------------- | ------------------------------------ |
| `/etc/udev/rules.d/99-roli-blocks.rules` | USB device permissions for your user |
| `~/.config/systemd/user/blocksd.service` | systemd user service with watchdog   |

## `blocksd uninstall`

Remove the systemd service and udev rules.

```bash
blocksd uninstall
```
