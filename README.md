<h1 align="center">
  <br>
  🔌 blocksd
  <br>
</h1>

<p align="center">
  <strong>Linux Daemon for ROLI Blocks Devices</strong><br>
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
  <a href="VISION.md">Vision</a>
</p>

---

ROLI Blocks devices need an active host-side handshake over MIDI SysEx to enter "API mode." Without it, they show a searching animation and eventually power off. There's no official Linux support.

**blocksd** implements the full ROLI Blocks protocol — device discovery, topology management, API mode keepalive, LED control, touch events, and device configuration — so your Blocks stay alive and useful on Linux.

## ✦ Features

| Capability | Description |
| --- | --- |
| 🔌 **API Mode Keepalive** | Periodic pings prevent the 5-second device timeout that kills API mode |
| 🏗️ **Topology Management** | Auto-discovers devices over USB, tracks DNA-connected blocks through master |
| 🎭 **Full State Machine** | Serial → topology → API activation → ping loop, matching the C++ reference |
| 💡 **LED Control** | Lightpad / Lightpad M RGB565 bitmap grid, CLI patterns (solid, gradient, rainbow, checkerboard) |
| 👆 **Touch & Button Events** | Normalized touch data (x/y/z/velocity) and button callbacks |
| ⚙️ **Device Config** | Read/write device settings (sensitivity, MIDI channel, scale, etc.) |
| 🔊 **DAW Friendly** | ALSA multi-client — blocksd and your DAW share MIDI without conflict |
| 🛡️ **systemd Integration** | Type=notify service, watchdog heartbeat, udev rules for plug-and-play |

## 📦 Install

### From PyPI

```bash
uv tool install blocksd
blocksd install    # sets up systemd service + udev rules
```

### From Source

```bash
git clone https://github.com/hyperb1iss/blocksd.git
cd blocksd
uv sync
uv run blocksd install
```

The `install` command sets up:
- **udev rules** — proper permissions for ROLI USB devices (requires sudo)
- **systemd user service** — auto-starts on login with watchdog monitoring
- **Security hardening** — sandboxed with `ProtectSystem=strict`, `NoNewPrivileges`, etc.

## ⚡ Usage

### Running the Daemon

```bash
# Foreground with verbose logging
blocksd run -v

# As a systemd service (after install)
systemctl --user start blocksd
systemctl --user status blocksd
journalctl --user -u blocksd -f
```

When running, you'll see devices connect:

```
INFO  blocksd ready — scanning for ROLI devices
INFO  Master serial: LKBC9PZSOH978HOE
INFO  Topology: 2 devices, 1 connections
INFO  ✨ Device connected: lumi_keys_block (LKBC9PZSOH978HOE) — battery 31%
INFO  ✨ Device connected: lightpad_block_m (LPMJW6SWHSPD8H92) — battery 31%
```

### Device Status

```bash
# Quick scan — shows detected MIDI ports
blocksd status

# Full probe — connects to devices, shows type/serial/battery/version
blocksd status --probe
```

### LED Control

Control the 15×15 LED grid on Lightpad Block and Lightpad Block M:

```bash
blocksd led solid '#ff00ff'                          # solid color
blocksd led rainbow                                   # animated rainbow
blocksd led gradient ff0000 0000ff                    # horizontal gradient
blocksd led gradient ff0000 0000ff --vertical         # vertical gradient
blocksd led checkerboard ff0000 00ff00                # 2×2 checkerboard
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

### Service Management

```bash
blocksd install                        # install systemd service + udev rules
blocksd install --no-udev              # skip udev rules
blocksd install --no-enable            # install but don't auto-start
blocksd uninstall                      # remove everything
```

## 🔌 External API

`blocksd` exposes a Unix socket API for external clients like Hypercolor.

- Socket path: `$XDG_RUNTIME_DIR/blocksd/blocksd.sock`
- Fallback path: `/tmp/blocksd/blocksd.sock`
- One socket supports both control messages and high-rate LED frame writes

The quick rules:

- Use `discover` first to get the device `uid`
- Only stream frames to devices advertising nonzero `grid_width` and
  `grid_height` in discovery
- Use the fixed-size binary frame protocol for animation and streaming
- Treat `frame_ack.accepted=false` or binary ack `0x00` as a rejected write:
  this usually means the device is not ready yet, the `uid` is gone, or the
  payload was malformed
- Once a device is live, frame writes are coalesced daemon-side to the latest
  target state instead of surfacing host-visible “busy” backpressure
- Prefer a separate subscription socket if you also want events; outbound NDJSON
  events and 1-byte binary frame acks share the same connection

See [docs/API.md](docs/API.md) for the full protocol reference, examples, and
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
│   └── programs.py           BitmapLEDProgram (94-byte repaint)
├── topology/
│   ├── detector.py           MIDI port scanning
│   ├── device_group.py       connection lifecycle (the big one)
│   └── manager.py            orchestrates DeviceGroups
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

| Device | USB PID | Serial Prefix | Status |
| --- | --- | --- | --- |
| Lightpad Block / M | `0x0900` | `LPB` / `LPM` | ✅ Tested |
| LUMI Keys Block | `0x0E00` | `LKB` | ✅ Tested |
| Seaboard Block | `0x0700` | `SBB` | 🔲 Untested |
| Live Block | — | `LIC` | 🔲 Untested |
| Loop Block | — | `LOC` | 🔲 Untested |
| Developer Control Block | — | `DCB` | 🔲 Untested |
| Touch Block | — | `TCB` | 🔲 Untested |
| Seaboard RISE 25/49 | `0x0200` / `0x0210` | — | 🔲 Untested |

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

- [x] **Protocol Core** — 7-bit packing, checksum, SysEx builder/decoder
- [x] **Device Discovery** — MIDI port scanning, serial number parsing
- [x] **Topology Management** — multi-device tracking, DNA connections
- [x] **API Mode Keepalive** — full state machine with correct ping timing
- [x] **Remote Heap Manager** — ACK tracking, retransmission, heap state sync
- [x] **LittleFoot Programs** — bytecode assembler, BitmapLEDProgram upload
- [x] **CLI LED Commands** — `blocksd led solid #ff00ff`, `blocksd led rainbow`
- [x] **Touch/Button Events** — normalized callbacks with full velocity data
- [x] **Config Commands** — read/write device settings via CLI
- [x] **sd_notify Integration** — Type=notify service with watchdog heartbeat
- [x] **CI/CD** — GitHub Actions, PyPI publishing, automated releases
- [ ] **D-Bus Interface** — IPC for external applications
- [ ] **Hypercolor Integration** — ROLI Blocks as an RGB device backend

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
