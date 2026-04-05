# Quick Start

Five minutes from plug-in to LED rainbow. This guide walks you through connecting your first device, watching the protocol handshake in real time, and playing with the built-in tools.

## Connect a Device

Plug in a ROLI Block via USB. If you've run `blocksd install`, the udev rules are already in place and the device will be accessible without root.

## Run the Daemon

Start blocksd in the foreground with verbose logging to see what's happening:

```bash
blocksd run -v
```

You'll see the device discovery sequence play out:

```
INFO  blocksd ready, scanning for ROLI devices
INFO  Master serial: LKBC9PZSOH978HOE
INFO  Topology: 2 devices, 1 connections
INFO  ✨ Device connected: lumi_keys_block (LKBC9PZSOH978HOE), battery 31%
INFO  ✨ Device connected: lightpad_block_m (LPMJW6SWHSPD8H92), battery 31%
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

In a separate terminal, scan for connected devices:

```bash
blocksd status
```

For full details including serial number, firmware version, and battery level:

```bash
blocksd status --probe
```

## Try LED Patterns

If you have a Lightpad Block or Lightpad Block M, try the built-in LED patterns:

```bash
blocksd led solid '#ff00ff'                      # solid magenta
blocksd led rainbow                               # animated rainbow
blocksd led gradient ff0000 0000ff                # red → blue gradient
blocksd led gradient ff0000 0000ff --vertical     # vertical gradient
blocksd led checkerboard ff0000 00ff00            # 2x2 checkerboard
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

For a visual overview of your connected devices:

```bash
blocksd ui
```

This opens a real-time dashboard at `http://localhost:9010` showing device topology, battery status, and LED state. The dashboard communicates with the daemon over WebSocket.

```bash
blocksd ui --port 8080           # custom port
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
