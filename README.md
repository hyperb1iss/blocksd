# 🔌 blocksd

<div align="center">

**Linux daemon that keeps ROLI Blocks alive**

[![Python](https://img.shields.io/badge/Python-3.13+-3776ab?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-ISC-e135ff?style=for-the-badge)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Alpha-f1fa8c?style=for-the-badge)]()

[⚡ Quick Start](#-quick-start) · [🏗️ Architecture](#-architecture) · [🧪 Development](#-development) · [🔮 Vision](VISION.md)

</div>

---

ROLI Blocks devices (Lightpad, Seaboard Block, LUMI Keys, Live/Loop/Touch/Control blocks) need an active host-side handshake over MIDI SysEx to enter "API mode." Without it, they show a searching animation and eventually power off. ROLI's official software is Windows/macOS only.

**blocksd** is a Linux daemon that implements the full ROLI Blocks protocol — device discovery, topology management, API mode keepalive, and LED control — so your Blocks stay alive and useful on Linux.

## ✦ What It Does

| Capability | Description |
| --- | --- |
| 🔌 **API Mode Keepalive** | Periodic pings prevent the 5-second device timeout that kills API mode |
| 🏗️ **Topology Management** | Auto-discovers devices over USB, tracks DNA-connected blocks through master |
| 🎭 **Full State Machine** | Serial → topology → API activation → ping loop, matching the C++ reference |
| 💡 **LED Control** | RGB565 bitmap grid, built-in patterns (solid, gradient, rainbow, checkerboard) |
| 🔊 **DAW Friendly** | ALSA multi-client — blocksd and your DAW share MIDI without conflict |
| ⚙️ **systemd Integration** | User service with watchdog, udev rules for plug-and-play |

## 📦 Installation

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

# Run the daemon (foreground, verbose)
blocksd run -v

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
├── daemon.py                 asyncio main loop, signal handling
│   └── TopologyManager       polls MIDI ports every 1.5s
│       └── DeviceGroup       per-USB lifecycle state machine
│           └── MidiConnection    python-rtmidi wrapper (SysEx I/O)
├── protocol/                 pure protocol logic (no I/O, fully testable)
│   ├── constants.py          enums, headers, bit sizes
│   ├── checksum.py           SysEx checksum algorithm
│   ├── packing.py            7-bit pack/unpack (LSB-first)
│   ├── builder.py            host → device packet construction
│   ├── decoder.py            device → host packet parsing
│   ├── serial.py             serial number request/parse
│   └── data_change.py        SharedDataChange diff encoder
├── device/
│   ├── models.py             BlockType, DeviceInfo, Topology
│   ├── registry.py           serial prefix → device type mapping
│   └── connection.py         rtmidi ↔ asyncio bridge
├── led/
│   ├── bitmap.py             RGB565 LED grid (15×15 Lightpad)
│   └── patterns.py           solid, gradient, rainbow, checkerboard
├── topology/
│   ├── detector.py           MIDI port scanning
│   ├── device_group.py       connection lifecycle (the big one)
│   └── manager.py            orchestrates DeviceGroups
└── cli/
    ├── app.py                Typer commands (run, status)
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
uv run pytest                  # all tests (148 currently)
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

See [VISION.md](VISION.md) for the full vision, use cases, and ideas.

**Remaining work:**

- [ ] **Remote Heap Manager** — ACK tracking, retransmission, heap state sync
- [ ] **LittleFoot Program Upload** — compile/upload BitmapLEDProgram to device
- [ ] **CLI LED Commands** — `blocksd led solid #ff00ff`, `blocksd led rainbow`
- [ ] **Touch/Button Events** — expose via callback API or D-Bus
- [ ] **Config Commands** — read/write device settings
- [ ] **sd_notify Integration** — proper systemd watchdog heartbeat
- [ ] **D-Bus Interface** — IPC for external applications

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

[ISC](LICENSE) — free for any use.

---

<div align="center">
    ✦ Built with obsession by <a href="https://hyperbliss.tech"><strong>Hyperbliss</strong></a> ✦
</div>
