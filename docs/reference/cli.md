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

| Flag                      | Short     | Description                                        |
| ------------------------- | --------- | -------------------------------------------------- |
| `--verbose`               | `-v`      | Enable debug logging                               |
| `--foreground / --daemon` | `-f / -d` | Accepted for compatibility; both run in foreground |
| `--config`                |           | Path to TOML config file                           |

## `blocksd ui`

Open the running daemon's dashboard. Start the service or `blocksd run` first.

```bash
blocksd ui                       # open the existing dashboard
blocksd ui --no-browser          # print its URL
blocksd --socket /path/to/blocksd.sock ui
```

The daemon reports its configured dashboard address. Set `web_host` and `web_port` in the daemon configuration; the UI command does not change them or start another daemon.

## `blocksd status`

Read device information from the running daemon without opening MIDI ports.

```bash
blocksd status                  # device, serial, battery, firmware
blocksd status --probe          # include DNA connection count
```

Use the global `--socket PATH` option before the command to connect to a custom socket. Otherwise the client reads `api_socket` from the normal configuration locations, then uses the platform default.

## `blocksd led`

Control Lightpad grids and LUMI key colors. These commands send a frame through the running daemon and exit. Use `--device SERIAL` to select one device; otherwise lighting commands target every connected device with the requested surface. The first frame loads a LittleFoot renderer; pixel delivery waits for upload acknowledgement and a matching execution challenge reply (see [LittleFoot](../architecture/littlefoot)).

### `blocksd led solid`

Fill the entire grid with a single color.

```bash
blocksd led solid '#ff00ff'          # hex color (quote the hash for shell)
blocksd led solid ff00ff             # hash is optional
```

### `blocksd led rainbow`

Generate a static rainbow gradient across the grid.

```bash
blocksd led rainbow
blocksd led rainbow --brightness 0.5 # dimmer rainbow (0.0-1.0)
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
blocksd led checkerboard ff0000 00ff00             # 1x1 squares (default)
blocksd led checkerboard ff0000 00ff00 --size 3    # 3x3 squares
blocksd led checkerboard ff0000 00ff00 --size 5    # 5x5 squares
```

### `blocksd led off`

Turn off the Lightpad grid (fill with black).

```bash
blocksd led off
```

### `blocksd led keys`

Set all 24 LUMI key colors to a rainbow or a single hex color. Requires LUMI firmware 1.3.0 or newer; visible rendering has been verified on 1.3.9. The renderer retains the default musical key handler. Live MIDI/MPE preservation during lighting still needs a dedicated acceptance check.

```bash
blocksd led keys
blocksd led keys rainbow
blocksd led keys '#ff00ff'
blocksd led keys 000000              # key lights off
```

## `blocksd config`

Read reported configuration through the running daemon. Writes validate the device-reported range and wait for matching readback before reporting confirmation. A timeout or disconnect is an error, not a successful save. If multiple devices are connected, specify `--device SERIAL`; configuration commands never silently write to every device.

### `blocksd config list`

Show all known configuration item IDs and their descriptions.

```bash
blocksd config list
```

The list follows the system IDs in the [ROLI BLOCKS SDK](https://github.com/WeAreROLI/roli_blocks_basics/blob/212ba4e237638b9ae8c2a4f76dd2070110392031/blocks/roli_BlockConfigId.h). An ID in this list does not establish that your device or its current program supports it. Use device-reported values and ranges.

Earlier versions mislabeled several IDs. Update scripts that imported the Python enum or selected numeric IDs from the old list:

| Setting                    | Correct ID | Earlier mapping                                             |
| -------------------------- | ---------- | ----------------------------------------------------------- |
| Glide sensitivity          | 11         | 12                                                          |
| Slide sensitivity          | 12         | 11                                                          |
| MIDI mode (`midi_use_mpe`) | 2          | `midi_channel_mode` labeled ID 7, which is slide mode       |
| Mode                       | 20         | Labeled `grid_size`                                         |
| Chord                      | 24         | Labeled `colour_preset`                                     |
| MPE zone                   | 40         | 30, which is X tracking mode                                |
| MIDI start channel         | 0          | `mpe_channel_start` labeled ID 31, which is Y tracking mode |
| MIDI end channel           | 1          | `mpe_channel_end` labeled ID 32, which is Z tracking mode   |

The incorrect enum names were removed. Numeric config requests still send the supplied ID unchanged. Global key color, root key color, and hardware brightness use IDs 34, 35, and 36. The SDK describes hardware brightness on a 0 to 100 scale; the daemon's frame brightness control uses 0 to 255 and is a separate setting.

### `blocksd config get <id>`

Read a configuration value from the device.

```bash
blocksd config get 10            # read velocity sensitivity
```

### `blocksd config set <id> <value>`

Write a configuration value to the device.

```bash
blocksd config set 10 50 --device LKB1234567890AB
blocksd config set --device LKB1234567890AB 4 -- -1  # negative octave
```

## `blocksd install`

Set up a systemd user service and udev rules on Linux, or a per-user LaunchAgent on macOS. Only Linux udev installation requires sudo. macOS service registration requires a GUI login session.

```bash
blocksd install                  # native service + auto-start, plus Linux udev rules
blocksd install --no-udev        # skip udev rules
blocksd install --no-enable      # write service without enabling or restarting
blocksd install --no-service     # skip background service setup entirely
```

The Linux installer creates:

| File                                     | Purpose                              |
| ---------------------------------------- | ------------------------------------ |
| `/etc/udev/rules.d/99-roli-blocks.rules` | USB device permissions for your user |
| `~/.config/systemd/user/blocksd.service` | systemd user service with watchdog   |

The macOS installer creates `~/Library/LaunchAgents/tech.hyperbliss.blocksd.plist` and writes logs under `~/Library/Logs/blocksd/`. Repeated installation replaces the loaded service definition and starts the new executable. With `--no-enable`, macOS only writes the definition; Linux also reloads systemd. See [macOS installation](../guide/installation#macos) for stop, start, and status commands.

## `blocksd uninstall`

Remove the native background service and, on Linux, udev rules. The Python package, user configuration, and macOS logs remain; remove a uv tool installation separately with `uv tool uninstall blocksd`.

```bash
blocksd uninstall
```
