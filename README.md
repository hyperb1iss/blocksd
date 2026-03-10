<h1 align="center">
  <br>
  🔌 blocksd
  <br>
</h1>

<p align="center">
  <strong>Linux Daemon for ROLI Blocks Devices</strong><br>
  <sub>✦ Topology · Keepalive · LED Control ✦</sub>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.13+-3776ab?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/asyncio-Event_Loop-80ffea?style=for-the-badge&logo=python&logoColor=0a0a0f" alt="asyncio">
  <img src="https://img.shields.io/badge/MIDI-SysEx-ff6ac1?style=for-the-badge&logo=midi&logoColor=white" alt="MIDI">
  <img src="https://img.shields.io/badge/License-ISC-e135ff?style=for-the-badge" alt="License">
</p>

<p align="center">
  <a href="#-features">Features</a> •
  <a href="#-install">Install</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-architecture">Architecture</a> •
  <a href="#-supported-devices">Devices</a> •
  <a href="#-development">Development</a> •
  <a href="VISION.md">Vision</a>
</p>

---

ROLI Blocks devices need an active host-side handshake over MIDI SysEx to enter "API mode." Without it, they show a searching animation and eventually power off. There's no official Linux support.

**blocksd** implements the full ROLI Blocks protocol — device discovery, topology management, API mode keepalive, and LED control — so your Blocks stay alive and useful on Linux.

## ✦ Features

| Capability | Description |
| --- | --- |
| 🔌 **API Mode Keepalive** | Periodic pings prevent the 5-second device timeout that kills API mode |
| 🏗️ **Topology Management** | Auto-discovers devices over USB, tracks DNA-connected blocks through master |
| 🎭 **Full State Machine** | Serial → topology → API activation → ping loop, matching the C++ reference |
| 💡 **LED Control** | RGB565 bitmap grid, CLI patterns (solid, gradient, rainbow, checkerboard) |
| 👆 **Touch & Button Events** | Normalized touch data (x/y/z/velocity) and button callbacks |
| ⚙️ **Device Config** | Read/write device settings (sensitivity, MIDI channel, scale, etc.) |
| 🔊 **DAW Friendly** | ALSA multi-client — blocksd and your DAW share MIDI without conflict |
| 🛡️ **systemd Integration** | Type=notify service, watchdog heartbeat, udev rules for plug-and-play |

## 📦 Install

### From Source (Recommended)

```bash
git clone https://github.com/hyperb1iss/blocksd.git
cd blocksd
uv sync
uv run blocksd install    # sets up systemd service + udev rules
```

### Manual

```bash
uv sync
uv run blocksd run        # run in foreground
```

## ⚡ Quick Start

```bash
# Check for connected devices
blocksd status

# Probe devices for full info (serial, battery, type)
blocksd status --probe

# Run the daemon (foreground, verbose)
blocksd run -v

# Set LED patterns
blocksd led solid '#ff00ff'
blocksd led rainbow
blocksd led gradient ff0000 0000ff --vertical
blocksd led checkerboard ff0000 00ff00 --size 3
blocksd led off

# Device configuration
blocksd config list                    # show all config IDs
blocksd config get 10                  # read velocity sensitivity
blocksd config set 10 50               # write velocity sensitivity

# Install as a systemd user service
sudo blocksd install

# Remove systemd service + udev rules
sudo blocksd uninstall
```

When running, you'll see devices connect:

```
INFO  blocksd ready — scanning for ROLI devices
INFO  Master serial: LKBC9PZSOH978HOE
INFO  Topology: 2 devices, 1 connections
INFO  ✨ Device connected: lumi_keys_block (LKBC9PZSOH978HOE) — battery 31%
INFO  ✨ Device connected: lightpad_block_m (LPMJW6SWHSPD8H92) — battery 31%
```

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

## 🧪 Development

### Setup

```bash
uv sync                       # install all dependencies
```

### Testing

```bash
uv run pytest                  # all tests (275 currently)
uv run pytest -v               # verbose
uv run pytest tests/protocol/  # specific module
```

### Linting & Types

```bash
uv run ruff check .            # lint
uv run ruff format .           # format
uv run ty check                # type check
```

### Project Layout

- **Source:** `src/blocksd/`
- **Tests:** `tests/` (mirrors source structure)
- **systemd:** `systemd/blocksd.service`, `systemd/99-roli-blocks.rules`
- **Firmware:** `firmware/default/*.littlefoot` (reference LittleFoot programs)

## 🗺️ Roadmap

See [VISION.md](VISION.md) for the full vision, use cases, and ideas beyond music.

**Remaining work:**

- [x] **Remote Heap Manager** — ACK tracking, retransmission, heap state sync
- [x] **LittleFoot Program Upload** — compile/upload BitmapLEDProgram to device
- [x] **CLI LED Commands** — `blocksd led solid #ff00ff`, `blocksd led rainbow`
- [x] **Touch/Button Events** — normalized callbacks with full velocity data
- [x] **Config Commands** — read/write device settings via CLI
- [x] **sd_notify Integration** — Type=notify service with watchdog heartbeat
- [ ] **D-Bus Interface** — IPC for external applications
- [ ] **Hypercolor Integration** — ROLI Blocks as an RGB device backend

## 💜 Contributing

Contributions welcome! The protocol layer is fully implemented and tested — the best areas to contribute are LED control, touch event handling, and the D-Bus interface.

```bash
# development workflow
uv sync
uv run pytest               # make sure tests pass
uv run ruff check .         # lint clean
uv run ty check             # types clean
```

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
