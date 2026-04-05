# 🔮 blocksd — Vision & Use Cases

> _These are precision touch surfaces with pressure sensitivity, LED feedback, and mesh networking. Why limit them to music?_

---

## What We're Building

**blocksd** is a Linux daemon that brings full ROLI Blocks support to Linux. ROLI's official software is Windows/macOS only — on Linux, these devices show a searching animation and eventually power off since there's no host-side driver to activate API mode.

We're building the full protocol stack: device discovery, topology management, API mode keepalive, LED control, touch/pressure input, and eventually LittleFoot program upload. The goal is complete parity with the original ROLI drivers, plus capabilities they never shipped.

### What Makes These Devices Special

- **15×15 RGB LED matrix** (Lightpad) with individual pixel control
- **Continuous pressure-sensitive touch surface** — not just on/off, but X, Y, Z (pressure) with velocity
- **DNA mesh networking** — blocks snap together magnetically and form a topology
- **Low-latency USB MIDI** — sub-millisecond response times
- **Compact, bus-powered** — no external power needed
- **Modular** — mix Lightpads, Seaboard strips, control surfaces, loop blocks

---

## 🎯 Core Use Cases

### 1. Music Production on Linux

The obvious one. Linux has a thriving audio production ecosystem (Ardour, Bitwig, Reaper, Renoise, LMMS, SuperCollider, Pure Data) but zero ROLI Blocks support. blocksd bridges this gap.

- **MPE controller** — Blocks already output MPE MIDI natively, but without API mode keepalive they reset every 5 seconds
- **LED feedback from DAW** — map track colors, clip launch status, or mixer levels to the Lightpad grid
- **Custom control surfaces** — program buttons, sliders, and XY pads across multiple connected blocks
- **Live performance** — reliable keepalive means blocks won't die mid-set

### 2. Visual Instrument / Light Controller

The Lightpad's 15×15 LED grid + pressure-sensitive surface makes it a natural fit for lighting control.

- **DMX/ArtNet bridge** — use the Lightpad as a compact, portable lighting desk
- **Home Assistant integration** — control smart lights with pressure gestures (press harder = brighter)
- **LED art installation controller** — map pressure patterns to external LED strips via WLED/SignalRGB
- **VJ tool** — trigger visual effects with touch, see previews on the Lightpad grid
- **Stage lighting** — snap together multiple Lightpads for a modular control surface

### 3. Developer Tool / Status Dashboard

A glanceable 15×15 pixel display sitting on your desk, driven by any script.

- **CI/CD status board** — green/red grid showing build status across repos
- **System monitor** — CPU cores as pixels (color = load), memory usage as a bar
- **Pomodoro timer** — visual countdown with pressure to pause/skip
- **Notification beacon** — flash patterns for Slack mentions, PR reviews, deploy alerts
- **Git heatmap** — commit activity visualization, live updated
- **Network monitor** — latency/throughput for homelab services as a color grid

### 4. Creative Coding Canvas

The Lightpad as a tiny programmable display for generative art.

- **Processing/p5.js bridge** — render sketches to the physical LED grid
- **Conway's Game of Life** — touch to seed cells, watch evolution in RGB
- **Reaction-diffusion** — real-time Turing patterns on hardware LEDs
- **Pixel art editor** — draw with pressure sensitivity, export as sprites
- **Shader playground** — write GLSL-like programs that run on the LED grid
- **Math visualizer** — fractals, cellular automata, strange attractors at 15×15

### 5. Accessibility Input Device

Continuous pressure sensitivity opens doors for adaptive input.

- **Pressure-based text input** — map pressure zones to characters or words
- **Gesture recognition** — train custom gestures for system control
- **Haptic feedback companion** — LED patterns confirm input without looking
- **Switch-accessible interface** — large touch zones with visual confirmation
- **Communication board** — pressure-sensitive AAC device with LED symbols

### 6. Gaming & Interactive Toys

Low latency + tactile feedback + LEDs = fun.

- **Simon Says** — classic memory game with full-color LED sequences
- **Whack-a-mole** — tap the lit squares before they disappear
- **Puzzle games** — sliding tiles, Tetris, maze navigation on the grid
- **Tabletop RPG companion** — miniature battle map with touch-to-move
- **Rhythm game pad** — Dance Dance Revolution for your fingertips
- **Collaborative drawing** — two connected Lightpads, each player draws on their own

### 7. Smart Home Control Surface

A physical, tactile interface for home automation.

- **Room controller** — each zone of the grid maps to a room, pressure = brightness
- **Scene launcher** — tap patterns to trigger Home Assistant scenes
- **Thermostat** — slide up/down for temperature, LED color shows current temp
- **Media remote** — transport controls with visual playback state
- **Security panel** — pattern-based unlock code with LED confirmation

---

## 🧪 Experimental Ideas

### Multi-Block Configurations

DNA mesh networking means blocks snap together and form a unified surface. With topology awareness, blocksd can treat N×1 or 2×2 arrangements as a single logical surface.

- **30×15 panoramic display** — two Lightpads side by side
- **15×30 vertical display** — two Lightpads stacked
- **Mixed surfaces** — Lightpad for display + Seaboard Block for continuous pitch input
- **Control surface cluster** — Live Block buttons + Lightpad for visual feedback

### D-Bus / IPC Interface

Expose the full device API over D-Bus so any Linux application can:

- Read touch events (X, Y, Z, velocity) as a stream
- Set individual LED pixels or upload full frames
- Query device topology, battery, firmware version
- Subscribe to connect/disconnect events

This turns blocksd from a daemon into a platform. Write a quick Python script that reads touch events and controls Philips Hue lights. Or a Rust app that renders GPU shader output to the LED grid.

### LittleFoot Programs

The devices run LittleFoot — a simple bytecode VM. Programs uploaded to the device execute locally, enabling:

- **Standalone LED animations** — patterns that run on the device without host
- **Local touch processing** — filter or transform touch data before it reaches the host
- **Latency-critical feedback** — LED response to touch without USB round-trip
- **Device-side state machines** — modes, presets, configuration stored on the block

### WebSocket / HTTP API

Expose device state and control over HTTP for browser-based interfaces:

- **Web dashboard** — real-time device status, battery, topology visualization
- **Remote LED control** — paint on the grid from a phone browser
- **Integration hub** — webhook triggers on touch events for IFTTT/n8n/Node-RED
- **Classroom tool** — teacher sends patterns to student blocks over the network

---

## 🛠️ Implementation Phases

### Completed

- [x] **Protocol Core** — 7-bit packing, checksum, SysEx framing
- [x] **Packet Builder/Decoder** — all host↔device message types
- [x] **Connection Layer** — rtmidi wrapper, port scanning, asyncio bridge
- [x] **Topology Management** — device discovery, DNA mesh, state machine
- [x] **API Mode Keepalive** — ping loop with master/DNA intervals
- [x] **LED Grid & Patterns** — RGB565 bitmap, Color type, built-in patterns
- [x] **DataChange Encoder** — diff-based heap writes with RLE
- [x] **systemd/udev** — user service, device rules, install/uninstall CLI
- [x] **Remote Heap Manager** — ACK-tracked heap state, retransmission, in-flight budgets
- [x] **LittleFoot Assembler** — bytecode assembler with label resolution and FNV1a function hashing
- [x] **CLI LED Commands** — `blocksd led solid #ff00ff`, rainbow, gradient, checkerboard
- [x] **Touch & Button Events** — normalized pressure/velocity callbacks
- [x] **Config Commands** — device settings read/write via CLI
- [x] **sd_notify Integration** — Type=notify service with watchdog heartbeat
- [x] **Unix Socket API** — NDJSON + binary frame protocol for external clients
- [x] **WebSocket & HTTP API** — browser-based control, monitoring, and LED streaming
- [x] **Web Dashboard** — `blocksd ui` launches a real-time device status interface

### In Progress

- [ ] **LittleFoot Program Upload** — BitmapLEDProgram bytecode to device memory (blocked by firmware opcode incompatibility on v1.1.0 — `getHeapBits` and `dupOffset` crash the VM; assembler and programs are complete, upload is disabled pending firmware fix)

### Planned

- [ ] **D-Bus Interface** — IPC for desktop integration
- [ ] **Multi-block Surfaces** — unified coordinate space across DNA topology
- [ ] **Hypercolor Integration** — ROLI Blocks as an RGB device backend

### Aspirational

- [ ] **LittleFoot Compiler** — compile programs from source (not just bytecode)
- [ ] **Plugin System** — loadable modules for different use cases
- [ ] **SignalRGB Bridge** — cross-device RGB synchronization
- [ ] **Home Assistant Integration** — native HA component
- [ ] **OSC Support** — Open Sound Control protocol for creative tools

---

## 💜 Why This Matters

ROLI still actively ships and supports Blocks on Windows and macOS — but Linux gets nothing. The protocol is undocumented and everything in blocksd was reverse-engineered from extracted ROLI Connect installers and JUCE SDK source.

blocksd brings full Blocks support to Linux. With a clean protocol implementation and a daemon that handles the lifecycle, these devices become a platform for whatever you can imagine — on the OS of your choice.

The 15×15 LED grid on a Lightpad is small. But it's physical, tactile, and sitting right there on your desk. Sometimes the most useful display isn't the one with the most pixels — it's the one you can reach out and touch.

---

<div align="center">

_Blocks on Linux — because your OS shouldn't limit your hardware._

</div>
