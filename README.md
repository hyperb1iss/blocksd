<h1 align="center">
  <br>
  🔌 blocksd
  <br>
</h1>

<p align="center">
  <strong>Linux and macOS Daemon for ROLI Blocks Devices</strong><br>
  <sub>✦ Topology · Keepalive · LED Control · Touch Events ✦</sub>
</p>

<p align="center">
  <a href="https://github.com/hyperb1iss/blocksd/actions/workflows/ci.yml"><img src="https://github.com/hyperb1iss/blocksd/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/blocksd/"><img src="https://img.shields.io/pypi/v/blocksd?color=e135ff" alt="PyPI"></a>
  <img src="https://img.shields.io/badge/Python-3.13+-3776ab?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/License-ISC-e135ff" alt="License">
</p>

<p align="center">
  <a href="#-features">Features</a> •
  <a href="#-install">Install</a> •
  <a href="#-usage">Usage</a> •
  <a href="#-external-api">External API</a> •
  <a href="#-architecture">Architecture</a> •
  <a href="#-supported-devices">Devices</a> •
  <a href="#-development">Development</a> •
  <a href="https://hyperb1iss.github.io/blocksd/">Docs</a> •
  <a href="VISION.md">Vision</a>
</p>

---

ROLI Blocks devices need an active host-side handshake over MIDI SysEx to enter "API mode." Without it, they show a searching animation and eventually power off. There's no official Linux support.

**blocksd** implements the ROLI Blocks host protocol: device discovery, topology management, API mode keepalive, LED control, touch events, and device configuration. The shared runtime uses ALSA on Linux and CoreMIDI on macOS.

## ✦ Features

| Capability                   | Description                                                                                     |
| ---------------------------- | ----------------------------------------------------------------------------------------------- |
| 🔌 **API Mode Keepalive**    | Periodic pings prevent the 5-second device timeout that kills API mode                          |
| 🏗️ **Topology Management**   | Auto-discovers devices over USB, tracks DNA-connected blocks through master                     |
| 🎭 **Full State Machine**    | Serial → topology → API activation → ping loop, matching the C++ reference                      |
| 💡 **LED Control**           | Lightpad / Lightpad M RGB565 bitmap grid, CLI patterns (solid, gradient, rainbow, checkerboard) |
| 👆 **Touch & Button Events** | Normalized touch data (x/y/z/velocity) and button callbacks                                     |
| ⚙️ **Device Config**         | Read/write device settings (sensitivity, MIDI channel, scale, etc.)                             |
| 🔊 **DAW Friendly**          | ALSA multi-client, blocksd and your DAW share MIDI without conflict                             |
| 🛡️ **systemd Integration**   | Type=notify service, watchdog heartbeat, udev rules for plug-and-play                           |

## 📦 Install

### macOS

macOS support is available from source until the next release. Build the dashboard, then run in the foreground:

```bash
git clone https://github.com/hyperb1iss/blocksd.git
cd blocksd
uv sync --locked
pnpm --dir web install --frozen-lockfile
pnpm --dir web build
uv run --locked blocksd run -v
```

After stopping the foreground process, run `uv run --locked blocksd install` to install a per-user LaunchAgent that starts on login. macOS does not need udev rules or sudo. Keep the checkout and its virtual environment at the installed path.

The macOS runtime and installer have automated coverage. USB LUMI Keys and a DNA-connected Lightpad Block M have been confirmed entering API mode. Sleep/wake and DAW coexistence still need hardware validation. See the [macOS installation guide](https://hyperb1iss.github.io/blocksd/guide/installation#macos) for service commands, Homebrew packaging status, and the hardware checklist.

### Quick Install

```bash
curl -fsSL https://github.com/hyperb1iss/blocksd/releases/latest/download/install.sh -o install-blocksd.sh
bash install-blocksd.sh
```

The current release installer targets Linux. It installs or upgrades blocksd using uv and managed Python, installs udev rules with sudo, and enables and restarts a systemd user service. Run as your normal user. Use `--version 0.5.0` to select a release or `--no-udev`, `--no-service`, and `--no-enable` to skip setup steps. See the [installation guide](https://hyperb1iss.github.io/blocksd/guide/installation) for prerequisites and upgrade details.

### From PyPI

```bash
uv tool install --python 3.13 blocksd
blocksd install    # sets up systemd service + udev rules
```

### Arch Linux

Packaging recipes live in `packaging/aur/`. AUR publication is separate from a GitHub or PyPI release; check the package's availability before installing through an AUR helper.

### From Source

```bash
git clone https://github.com/hyperb1iss/blocksd.git
cd blocksd
just install
just web-build
uv run --locked blocksd install
```

The `install` command sets up:

- **udev rules**: proper permissions for ROLI USB devices (requires sudo)
- **systemd user service**: auto-starts on login with watchdog monitoring
- **Security hardening**: sandboxed with `ProtectSystem=strict`, `NoNewPrivileges`, etc.

## ⚡ Usage

The current daemon does not upload its LittleFoot LED renderer (firmware opcode compatibility remains unresolved). LED commands and API frames can update heap data, but an accepted write does not establish visible LED output. See the [LittleFoot notes](https://hyperb1iss.github.io/blocksd/architecture/littlefoot).

### Running the Daemon

```bash
# Foreground with verbose logging
systemctl --user stop blocksd   # if the service is installed
blocksd run -v

# As a systemd service (after install)
systemctl --user start blocksd
systemctl --user status blocksd
journalctl --user -u blocksd -f
```

When running, you'll see devices connect:

```
INFO  blocksd ready, scanning for ROLI devices
INFO  Master serial: LKBC9PZSOH978HOE
INFO  Topology: 2 devices, 1 connections
INFO  ✨ Device connected: lumi_keys_block (LKBC9PZSOH978HOE), battery 31%
INFO  ✨ Device connected: lightpad_block_m (LPMJW6SWHSPD8H92), battery 31%
```

### Device Status

```bash
# Quick scan, shows detected MIDI ports
blocksd status

# Full probe, connects to devices, shows type/serial/battery/version
systemctl --user stop blocksd   # also stop any foreground daemon
blocksd status --probe
systemctl --user start blocksd
```

### LED Control

The LED and config commands open their own MIDI sessions. Stop the service and any foreground daemon before using them. LED commands remain running until Ctrl+C; config commands probe for about eight seconds. Restart the service afterward.

Control the 15×15 LED grid on Lightpad Block and Lightpad Block M:

```bash
blocksd led solid '#ff00ff'                          # solid color
blocksd led rainbow                                   # static rainbow
blocksd led gradient ff0000 0000ff                    # horizontal gradient
blocksd led gradient ff0000 0000ff --vertical         # vertical gradient
blocksd led checkerboard ff0000 00ff00                # 1x1 checkerboard
blocksd led checkerboard ff0000 00ff00 --size 3       # 3×3 checkerboard
blocksd led off                                       # lights off
```

### Device Configuration

Read and write device settings like velocity sensitivity, MIDI channel, scale mode, and more:

```bash
blocksd config list                    # show all known config IDs
blocksd config get 10                  # read velocity sensitivity
blocksd config set 10 50               # write velocity sensitivity
```

### Web Dashboard

If blocksd is already running, open `http://localhost:9010` directly. Use `blocksd ui` only when no daemon is running; the command starts its own daemon.

```bash
blocksd ui                             # start a daemon and open its dashboard
blocksd ui --port 8080                 # custom port
```

Opens a real-time dashboard showing connected devices, topology, battery status, and LED state. Uses WebSocket for live updates.

### Service Management

```bash
blocksd install                        # install systemd service + udev rules
blocksd install --no-udev              # skip udev rules
blocksd install --no-enable            # write/reload without starting or restarting
blocksd uninstall                      # remove service and udev rules
```

## 🔌 External API

`blocksd` exposes two APIs for external integration:

**Unix Socket**: low-latency IPC for local clients (e.g. Hypercolor)

- Socket path: `$XDG_RUNTIME_DIR/blocksd/blocksd.sock`
- Fallback path: `/tmp/blocksd/blocksd.sock`
- macOS path: `/tmp/blocksd-<uid>/blocksd.sock` in a private per-user directory
- One socket supports both control messages and high-rate LED frame writes

**WebSocket**: browser and network clients (used by `blocksd ui`)

- Default: `ws://localhost:9010/ws`
- Binary LED frame writes + JSON device events

The quick rules:

- Use `discover` first to get the device `uid`
- Only stream frames to devices advertising nonzero `grid_width` and
  `grid_height` in discovery
- Use the fixed-size binary frame protocol for animation and streaming
- Treat `frame_ack.accepted=false` or binary ack `0x00` as a rejected write:
  this usually means the device is not ready yet, the `uid` is gone, or the
  payload was malformed
- Once a device is live, frame writes are coalesced daemon-side to the latest
  target state instead of surfacing host-visible "busy" backpressure
- Prefer a separate subscription socket if you also want events; outbound NDJSON
  events and 1-byte binary frame acks share the same connection

See the [API reference](https://hyperb1iss.github.io/blocksd/reference/api) for the full protocol reference, examples, and
Hypercolor-oriented integration notes.

## 🏗️ Architecture

```
blocksd
├── daemon.py                 asyncio main loop, sd_notify, signal handling
│   └── TopologyManager       polls MIDI ports every 1.5s
│       └── DeviceGroup       per-USB lifecycle + touch/button/config events
│           └── MidiConnection    python-rtmidi wrapper (SysEx I/O)
├── protocol/                 pure protocol logic (no I/O, fully testable)
│   ├── constants.py          enums, headers, bit sizes
│   ├── checksum.py           SysEx checksum algorithm
│   ├── packing.py            7-bit pack/unpack (LSB-first)
│   ├── builder.py            host → device packet construction
│   ├── decoder.py            device → host packet parsing
│   ├── serial.py             serial number request/parse
│   ├── data_change.py        SharedDataChange diff encoder
│   └── remote_heap.py        ACK-tracked heap manager for live updates
├── device/
│   ├── models.py             BlockType, DeviceInfo, TouchEvent, ButtonEvent
│   ├── config_ids.py         known configuration item IDs
│   ├── registry.py           serial prefix → device type mapping
│   └── connection.py         rtmidi ↔ asyncio bridge
├── led/
│   ├── bitmap.py             RGB565 LED grid (15×15 Lightpad)
│   └── patterns.py           solid, gradient, rainbow, checkerboard
├── littlefoot/
│   ├── opcodes.py            LittleFoot VM opcode definitions
│   ├── assembler.py          bytecode assembler with label support
│   └── programs.py           BitmapLEDProgram (100-byte repaint)
├── topology/
│   ├── detector.py           MIDI port scanning
│   ├── device_group.py       connection lifecycle (the big one)
│   └── manager.py            orchestrates DeviceGroups
├── api/
│   ├── commands.py           shared command validation and dispatch
│   ├── server.py             Unix socket + WebSocket servers
│   ├── protocol.py           NDJSON + binary frame wire protocol
│   ├── events.py             event broadcaster (device/touch/button/config)
│   ├── websocket.py          RFC 6455 frame codec
│   └── http.py               HTTP parser + static file serving
├── web/                      web dashboard (Vite build output)
├── config/
│   ├── schema.py             DaemonConfig (Pydantic)
│   └── loader.py             TOML config file parsing
├── sdnotify.py               lightweight systemd notification (no deps)
└── cli/
    ├── app.py                Typer commands (run, status --probe)
    ├── led.py                LED pattern commands (solid, rainbow, etc.)
    ├── config.py             device config get/set/list
    └── install.py            systemd/udev setup
```

### Protocol Pipeline

```
Host                                          Device
 │                                              │
 │  ── Serial Dump Request ──────────────────►  │
 │  ◄─────────────────── Serial Response ────  │
 │  ── Request Topology ─────────────────────►  │
 │  ◄───────────────────── Topology ─────────  │
 │  ── endAPIMode + beginAPIMode ────────────►  │
 │  ◄──────────────────── Packet ACK ────────  │
 │                                              │
 │  ── Ping (400ms master / 1666ms DNA) ─────► │  ← keepalive loop
 │  ◄──────────────────── Packet ACK ────────  │
 │                                              │
 │  ── SharedDataChange (LED data) ──────────► │  ← heap writes
 │  ◄──────────────────── Packet ACK ────────  │
```

### Supported Devices

| Device                  | USB PID             | Serial Prefix | Status      |
| ----------------------- | ------------------- | ------------- | ----------- |
| Lightpad Block / M      | `0x0900`            | `LPB` / `LPM` | ✅ Tested   |
| LUMI Keys Block         | `0x0E00`            | `LKB`         | ✅ Tested   |
| Seaboard Block          | `0x0700`            | `SBB`         | 🔲 Untested |
| Live Block              | Unknown             | `LIC`         | 🔲 Untested |
| Loop Block              | Unknown             | `LOC`         | 🔲 Untested |
| Developer Control Block | Unknown             | `DCB`         | 🔲 Untested |
| Touch Block             | Unknown             | `TCB`         | 🔲 Untested |
| Seaboard RISE 25/49     | `0x0200` / `0x0210` | N/A           | 🔲 Untested |

Bitmap LED streaming is currently exposed for Lightpad Block / Lightpad Block M
only. Other devices are still discoverable and supported by the topology/API
state machine, but they do not advertise a bitmap frame surface.

## 🧪 Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full development guide.

```bash
uv sync                        # install all dependencies
uv run pytest                  # run tests
uv run ruff check .            # lint
uv run ruff format --check .   # format check
uv run ty check                # type check
```

## 🗺️ Roadmap

See [VISION.md](VISION.md) for the full vision, use cases, and ideas beyond music.

- [x] **Protocol Core**: 7-bit packing, checksum, SysEx builder/decoder
- [x] **Device Discovery**: MIDI port scanning, serial number parsing
- [x] **Topology Management**: multi-device tracking, DNA connections
- [x] **API Mode Keepalive**: full state machine with correct ping timing
- [x] **Remote Heap Manager**: ACK tracking, retransmission, heap state sync
- [x] **LittleFoot Assembler**: bytecode generation and BitmapLEDProgram definition
- [ ] **LittleFoot Upload**: firmware-compatible renderer for visible LED output
- [x] **CLI LED Commands**: `blocksd led solid '#ff00ff'`, `blocksd led rainbow`
- [x] **Touch/Button Events**: normalized callbacks with full velocity data
- [x] **Config Commands**: read/write device settings via CLI
- [x] **sd_notify Integration**: Type=notify service with watchdog heartbeat
- [x] **CI/CD**: GitHub Actions, PyPI publishing, automated releases
- [ ] **D-Bus Interface**: IPC for external applications
- [ ] **Hypercolor Integration**: ROLI Blocks as an RGB device backend

## ⚖️ License

[ISC](LICENSE)

---

<p align="center">
  <a href="https://github.com/hyperb1iss/blocksd">
    <img src="https://img.shields.io/github/stars/hyperb1iss/blocksd?style=social" alt="Star on GitHub">
  </a>
  &nbsp;&nbsp;
  <a href="https://ko-fi.com/hyperb1iss">
    <img src="https://img.shields.io/badge/Ko--fi-Support%20Development-ff5e5b?logo=ko-fi&logoColor=white" alt="Ko-fi">
  </a>
</p>

<p align="center">
  <sub>
    If blocksd keeps your Blocks alive, give us a ⭐ or <a href="https://ko-fi.com/hyperb1iss">support the project</a>
    <br><br>
    ✦ Built with obsession by <a href="https://hyperbliss.tech"><strong>Hyperbliss Technologies</strong></a> ✦
  </sub>
</p>
