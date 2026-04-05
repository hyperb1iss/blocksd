# Module Structure

Each module in blocksd has a clear responsibility and minimal coupling to its neighbors. This page documents what lives where and why.

## protocol/

The protocol package is the foundation. It contains pure, stateless functions for encoding and decoding the ROLI Blocks wire format.

### `constants.py`

All protocol enums, SysEx headers, USB product IDs, message type definitions, device commands, config commands, and bit size declarations. This is the single source of truth for protocol constants.

### `checksum.py`

The SysEx checksum algorithm: seed with data length, iterate with `checksum = checksum * 3 + byte`, mask to 7 bits.

### `packing.py`

The 7-bit packing engine. Provides `Packed7BitWriter` (for building outbound messages) and `Packed7BitReader` (for parsing inbound messages). Values are packed LSB-first, spanning byte boundaries as needed.

This is the highest-risk module in the codebase. Incorrect packing produces packets that the device silently ignores or misinterprets. It has extensive property-based tests using Hypothesis.

### `builder.py`

Constructs host-to-device packets. Takes message type, device index, and payload fields; returns a complete SysEx byte sequence including header, packed payload, checksum, and framing.

### `decoder.py`

Parses device-to-host packets. Strips SysEx framing, validates checksum, and decodes the 7-bit packed payload into structured message objects. Handles all device-to-host message types including topology, touch events, button events, ACKs, and config messages.

### `serial.py`

Serial number request/response handling. Builds the serial dump request packet and parses the response to extract the 16-character serial number.

### `data_change.py`

SharedDataChange encoder. Computes the diff between current and target heap state, then encodes it as a compact sequence of skip, set, and RLE commands. This is how LED pixel data and LittleFoot programs are uploaded to the device.

### `remote_heap.py`

ACK-tracked heap manager. Maintains the daemon-side view of what the device's heap contains, tracks in-flight data change packets, handles retransmission on timeout, and coalesces rapid updates into the latest target state.

## device/

### `models.py`

Pydantic models for device state: `BlockType` enum, `DeviceInfo`, `TouchEvent`, `ButtonEvent`, and `TopologyConnection`.

### `connection.py`

The python-rtmidi to asyncio bridge. Wraps MIDI input/output with a callback that marshals incoming SysEx messages to the event loop. Provides async send/receive methods for the rest of the codebase.

### `registry.py`

Maps serial number prefixes to `BlockType` values. Used during device identification to determine what kind of block we're talking to.

### `config_ids.py`

Known device configuration item IDs and their human-readable descriptions. Used by the `blocksd config list` command and for config sync.

## topology/

### `detector.py`

MIDI port scanning. Polls the system's MIDI ports looking for names that match ROLI's naming convention. Validates against USB vendor ID via sysfs as a secondary check.

### `device_group.py`

The big state machine. Manages the full lifecycle of a USB-connected device group: serial request, topology parsing, API mode activation, keepalive ping loop, touch/button event handling, and cleanup on disconnect. This is where most of the protocol complexity lives.

### `manager.py`

The TopologyManager orchestrates DeviceGroups. It runs the 1.5-second scan loop, creates DeviceGroups for new connections, and destroys them when connections are lost. It's the entry point that `daemon.py` calls.

## api/

### `server.py`

The API server entry point. Creates and manages the Unix socket server and optionally the WebSocket/HTTP server. Handles client connections, request routing, and LED frame dispatch.

### `protocol.py`

NDJSON and binary frame parsing/serialization. Distinguishes between binary frames (first byte `0xBD`) and JSON messages. Handles request/response mapping.

### `events.py`

EventBroadcaster. Pushes device, touch, and button events to subscribed clients. Manages per-client bounded queues and drops slow consumers to prevent server blocking.

### `websocket.py`

RFC 6455 WebSocket frame codec. Handles handshake, frame encoding/decoding, ping/pong, and close frames. No external WebSocket library dependency.

### `http.py`

Minimal HTTP parser and static file server. Serves the web dashboard's built static files and handles WebSocket upgrade requests.

## led/

### `bitmap.py`

The RGB565 LED grid. Provides a 15x15 pixel buffer with color conversion (RGB888 to RGB565), individual pixel access, and full-frame operations. Includes a `Color` type for hex color parsing.

### `patterns.py`

Built-in LED pattern generators: solid fill, horizontal/vertical gradient, rainbow, and checkerboard. Each generator returns a complete bitmap frame.

## littlefoot/

### `opcodes.py`

LittleFoot VM opcode definitions, register layout, and native function IDs. Based on the ROLI JUCE SDK source, with annotations for known firmware incompatibilities.

### `assembler.py`

Bytecode assembler with label resolution and FNV1a function name hashing. Converts assembly-like instructions into valid LittleFoot program binaries including the program header, function table, and checksum.

### `programs.py`

Pre-built LittleFoot programs. The primary one is BitmapLEDProgram: a 94-byte repaint routine that reads RGB565 pixel data from the heap and calls `fillPixel` for each pixel. Currently disabled due to firmware opcode incompatibility on v1.1.0.

## cli/

### `app.py`

The main Typer application. Defines top-level commands (`run`, `ui`, `status`) and registers subcommand groups (`led`, `config`, `install`, `uninstall`).

### `led.py`, `config.py`

LED pattern and device configuration CLI commands. These connect to the running daemon via the Unix socket API to execute operations.

### `install.py`

systemd service and udev rule installation/uninstallation. Generates the service file and udev rules from templates and writes them to the appropriate system locations.

## Other Modules

### `daemon.py`

The asyncio main loop. Creates the TopologyManager, starts the API server, handles signals (SIGINT, SIGTERM), and manages the sd_notify lifecycle.

### `config/schema.py` and `config/loader.py`

Pydantic-based configuration schema and TOML file loader. Validates and applies the daemon configuration.

### `sdnotify.py`

Lightweight systemd notification client. Sends `READY=1`, `WATCHDOG=1`, and status updates over the sd_notify socket without any external dependencies.
