# Module Structure

Each module in blocksd has a clear responsibility and minimal coupling to its neighbors. This page documents what lives where and why.

## protocol/

The protocol package is the foundation. It contains pure encoding and decoding functions plus stateful packing buffers and remote heap tracking, with no I/O.

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

Device state models: the `BlockType` enum and dataclasses including `DeviceInfo`, `TouchEvent`, `ButtonEvent`, and `DeviceConnection`.

### `connection.py`

The python-rtmidi to asyncio bridge. Wraps MIDI input/output with a callback that marshals incoming SysEx messages to the event loop. Provides synchronous sends and asynchronous receives for the rest of the codebase.

### `registry.py`

Maps serial number prefixes to `BlockType` values. Used during device identification to determine what kind of block we're talking to.

### `config_ids.py`

SDK system configuration IDs and their names, displayed by `blocksd config list`. Config synchronization and API requests use numeric IDs directly.

## topology/

### `detector.py`

MIDI port scanning. Polls the system's MIDI ports looking for names that match ROLI's naming convention. Pairs inputs and outputs by normalized name and occurrence; it does not inspect USB IDs.

### `device_group.py`

The big state machine. Manages the full lifecycle of a USB-connected device group: serial request, topology parsing, API mode activation, keepalive ping loop, touch/button event handling, and cleanup on disconnect. This is where most of the protocol complexity lives.

### `manager.py`

The TopologyManager orchestrates DeviceGroups. It runs the 1.5-second scan loop, creates DeviceGroups for new connections, and destroys them when connections are lost. It's the entry point that `daemon.py` calls.

## api/

### `commands.py`

Shared JSON and binary command handling for both transports. Each server has its own subscription and brightness state; validation and dispatch use one implementation.

### `server.py`

The API server entry point. Creates and manages the Unix socket server and optionally the WebSocket/HTTP server. Handles client connections, request routing, and LED frame dispatch.

### `protocol.py`

NDJSON and binary frame parsing/serialization. Distinguishes between binary frames (first byte `0xBD`) and JSON messages. Handles request/response mapping.

### `events.py`

EventBroadcaster. Pushes device, touch, and button events to subscribed clients. Manages per-client bounded queues and drops slow consumers to prevent server blocking.

### `websocket.py`

RFC 6455 WebSocket frame codec. Handles frame encoding/decoding, ping/pong, and close frames; the HTTP module handles the upgrade handshake. No external WebSocket library dependency.

### `http.py`

Minimal HTTP parser and static file server. Serves the web dashboard's built static files and handles WebSocket upgrade requests.

## led/

### `bitmap.py`

The RGB565 LED grid. Provides a 15x15 pixel buffer with color conversion (RGB888 to RGB565), individual pixel access, and full-frame operations. Includes a `Color` type for hex color parsing.

### `patterns.py`

Built-in LED pattern generators: solid fill, horizontal/vertical gradient, rainbow, and checkerboard. Each generator modifies the supplied grid.

## littlefoot/

### `opcodes.py`

LittleFoot VM opcode definitions, register layout, and native function IDs. Based on the ROLI JUCE SDK source, with annotations for known firmware incompatibilities.

### `assembler.py`

Bytecode assembler with label resolution and FNV1a function name hashing. Converts assembly-like instructions into valid LittleFoot program binaries including the program header, function table, and checksum.

### `programs.py`

Pre-built LittleFoot programs. The primary one is BitmapLEDProgram: a 100-byte repaint routine that reads RGB565 pixel data from the heap and calls `fillPixel` for each pixel. Currently disabled due to firmware opcode incompatibility on v1.1.0.

## cli/

### `app.py`

The main Typer application. Defines top-level commands (`run`, `ui`, `status`) and registers subcommand groups (`led`, `config`, `install`, `uninstall`).

### `led.py`, `config.py`

LED pattern and device configuration CLI commands. These create their own TopologyManager and access MIDI directly; they are not socket clients.

### `install.py`

systemd service and udev rule installation/uninstallation. Generates the service file and udev rules from templates and writes them to the appropriate system locations.

## Other Modules

### `daemon.py`

The asyncio main loop. Creates the TopologyManager, starts the API server, handles signals (SIGINT, SIGTERM), and manages the sd_notify lifecycle. Owns and joins the manager, shutdown waiter and watchdog tasks, and unwinds partially initialized servers when startup fails.

### `config/schema.py` and `config/loader.py`

Pydantic-based configuration schema and TOML file loader. Parses settings into DaemonConfig. API and web settings are applied; timing fields are currently not forwarded to the topology runtime.

### `sdnotify.py`

Lightweight systemd notification client. Sends `READY=1`, `WATCHDOG=1`, and status updates over the sd_notify socket without any external dependencies.
