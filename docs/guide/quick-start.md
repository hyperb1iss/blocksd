# Quick Start

Five minutes from plug-in to LED rainbow. This guide walks you through connecting your first device, watching the protocol handshake in real time, and playing with the built-in tools.

## Connect a Device

Plug in a ROLI Block via USB. If you've run `blocksd install`, the udev rules are already in place and the device will be accessible without root.

## Run the Daemon

Start blocksd in the foreground with verbose logging to see what's happening:

```bash
systemctl --user stop blocksd   # if the service is installed
blocksd run -v
```

You'll see the device discovery sequence play out:

```
INFO  blocksd ready, scanning for ROLI devices
INFO  Master serial: LKBC9PZSOH978HOE
INFO  Topology: 2 devices, 1 connections
INFO  ✨ Device connected: lumi_keys_block (LKBC9PZSOH978HOE), battery 100%
INFO  ✨ Device connected: lightpad_block_m (LPMJW6SWHSPD8H92), battery 100%
```

The daemon is now maintaining API mode keepalive. Your Blocks will stay alive as long as blocksd is running.

::: tip
If you installed the systemd service, you can also start the daemon in the background:

```bash
systemctl --user start blocksd
journalctl --user -u blocksd -f    # follow the logs
```

:::

## Check Device Status

In a separate terminal, query the running daemon:

```bash
blocksd status
```

For full details including serial number, firmware version, and battery level:

```bash
blocksd status --probe
```

## Try LED Patterns

The LED and config commands connect to the running daemon. Keep the service running. LED commands submit a frame and exit; configuration writes wait for device readback. Use `--device SERIAL` to select a device when more than one is connected.

The first LED frame loads a LittleFoot renderer. Pixels follow complete upload acknowledgement and a matching reply to a fresh execution challenge. Visible RGB patterns have been verified on Lightpad M 1.1.0 and LUMI 1.3.9. API acceptance confirms daemon acceptance, not a visible display change. See the [LittleFoot notes](../architecture/littlefoot).

If you have a Lightpad Block or Lightpad Block M, try the built-in LED patterns:

```bash
blocksd led solid '#ff00ff'                      # solid magenta
blocksd led rainbow                               # static rainbow
blocksd led gradient ff0000 0000ff                # red → blue gradient
blocksd led gradient ff0000 0000ff --vertical     # vertical gradient
blocksd led checkerboard ff0000 00ff00            # 1x1 checkerboard
blocksd led checkerboard ff0000 00ff00 --size 3   # 3x3 checkerboard
blocksd led off                                   # lights off
```

## Read Device Config

Query and modify device settings:

```bash
blocksd config list              # show all known config IDs
blocksd config get 10            # read velocity sensitivity
blocksd config set 10 50         # set velocity sensitivity to 50
```

## Launch the Web Dashboard

Run `blocksd ui` to open the existing daemon's dashboard. Start the service or `blocksd run` first; opening the UI does not create another hardware session.

For a visual overview of your connected devices:

```bash
blocksd ui
```

The dashboard opens at the daemon's configured address (normally `http://localhost:9010`). Select a device to adjust supported settings and save a preset. The presets page manages saved setups and reconnect restoration.

```bash
blocksd ui --no-browser          # print the running dashboard URL
```

## Running as a Service

For daily use, run blocksd as a systemd service so it starts automatically on login:

```bash
systemctl --user enable --now blocksd
```

Check the service status:

```bash
systemctl --user status blocksd
```

## What's Next

- [Configuration](./configuration): customize daemon behavior via TOML config
- [Web Dashboard](./web-dashboard): learn more about the real-time UI
- [CLI Reference](/reference/cli): all available commands
- [External API](/reference/api): integrate with your own applications
