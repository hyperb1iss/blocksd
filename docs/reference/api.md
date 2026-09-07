# External API

blocksd exposes two APIs for building your own integrations: a Unix domain socket for local IPC and a WebSocket for browser and network clients. Both share command validation and JSON payloads, but use different transport framing.

## Connection Methods

### Unix Socket

Low-latency local IPC. This is the preferred method for local integrations.

- Linux primary path: `$XDG_RUNTIME_DIR/blocksd/blocksd.sock`
- Linux fallback path: `/tmp/blocksd/blocksd.sock`
- macOS path: `/tmp/blocksd-<uid>/blocksd.sock`, using the current user's numeric ID
- Permissions: directory `0700`, socket `0660`

### WebSocket

Browser and network clients. Used by the web dashboard (`blocksd ui`).

- Default: `ws://localhost:9010/ws`
- Supports both binary LED frames and JSON messages

## Protocol Overview

On the Unix socket, a single connection can mix two message types:

- **NDJSON**: newline-delimited JSON for control messages and events
- **Binary LED frames**: fixed-size 685-byte packets for LED streaming

The server distinguishes inbound message types by the first byte:

- `0xBD`: binary LED frame
- Anything else: read as newline-delimited JSON

WebSocket clients send JSON in text messages and the same 685-byte LED packet in binary messages. Binary acknowledgements arrive as one-byte binary messages; JSON responses and events arrive as text messages. The custom WebSocket codec has not been validated against a full conformance suite.

## Recommended Client Strategy

1. Open a control socket
2. Send `discover` to get the device list and `uid` values
3. Use bitmap frames for nonzero grid dimensions; use JSON `key_frame` for `key_count = 24`
4. Use the binary frame path for Lightpad animation; LUMI key frames use JSON
5. Retry early frame rejections while the device is still coming up
6. Open a second socket for `subscribe` if you also need events

::: tip
Splitting control and event sockets avoids the complexity of demultiplexing binary frame acks (1 byte) and NDJSON event messages on the same connection.
:::

## Binary LED Frames

Use this for streaming, animations, and anything latency-sensitive.

### Frame Layout

Each binary frame is exactly **685 bytes**:

| Offset | Size  | Type     | Meaning                         |
| ------ | ----- | -------- | ------------------------------- |
| `0`    | `1`   | `u8`     | Magic `0xBD`                    |
| `1`    | `1`   | `u8`     | Message type `0x01`             |
| `2`    | `8`   | `u64 LE` | Device `uid`                    |
| `10`   | `675` | bytes    | `15 * 15 * 3` RGB888 pixel data |

Pixel order is row-major: pixel `i` maps to `x = i % 15`, `y = i // 15`. Each pixel is RGB888 on the wire; the daemon converts to device RGB565 internally.

### Binary Ack

Each parsed binary frame write returns one acknowledgement byte (inside a binary WebSocket message on that transport):

| Value  | Meaning  |
| ------ | -------- |
| `0x01` | Accepted |
| `0x00` | Rejected |

`0x00` means the device was unavailable, the `uid` was unknown, or the payload was invalid. Early rejections during device startup are retryable.

Acceptance confirms that the daemon accepted the frame, not a hardware acknowledgement or visible display change. The first frame triggers renderer upload and can remain queued until the code transfer is acknowledged and the renderer answers a fresh execution challenge. See [renderer startup](../architecture/littlefoot).

### Python Example

```python
import os
import socket
import struct

MAGIC = 0xBD
TYPE_FRAME = 0x01
PIXELS = bytes([255, 0, 0] * 225)  # solid red, 15x15 RGB888
uid = 42

frame = struct.pack("<BBQ", MAGIC, TYPE_FRAME, uid) + PIXELS

with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
    sock.connect(os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "blocksd/blocksd.sock"))
    sock.sendall(frame)
    accepted = sock.recv(1) == b"\x01"
    print("accepted:", accepted)
```

## JSON / NDJSON Protocol

JSON messages are newline-delimited UTF-8 JSON objects. Every request is one line, every response is one line.

### `ping`

Health check and basic daemon info.

```json
{ "type": "ping", "id": "req-1" }
```

```json
{
  "type": "pong",
  "version": "0.5.0",
  "uptime_seconds": 12,
  "device_count": 2,
  "id": "req-1"
}
```

### `discover`

List all connected devices with capabilities and battery status.

```json
{ "type": "discover", "id": "req-2" }
```

```json
{
  "type": "discover_response",
  "devices": [
    {
      "uid": 8456574102450706172,
      "serial": "LPMJW6SWHSPD8H92",
      "block_type": "lightpad_m",
      "name": "",
      "grid_width": 15,
      "grid_height": 15,
      "key_count": 0,
      "battery_level": 31,
      "battery_charging": false,
      "firmware_version": null
    }
  ],
  "id": "req-2"
}
```

The `uid` is a deterministic 64-bit identifier derived from the device serial. Clients can cache it across daemon restarts.

Only Lightpad Block and Lightpad Block M advertise nonzero grid dimensions and accept bitmap frames. LUMI advertises `grid_width = 0`, `grid_height = 0`, and `key_count = 24`; use `key_frame` for its key colors. Other recognized devices report `key_count = 0`.

::: warning
A device can appear in `discover_response` before API mode activation and heap setup finish. Retry rejected writes after discovery settles. An accepted frame can still be waiting for renderer initialisation; acceptance does not expose renderer readiness.
:::

### `frame`

JSON-based LED frame write. Supported for compatibility and debugging, but not recommended for streaming.

```json
{ "type": "frame", "uid": 42, "pixels": "...base64..." }
```

```json
{ "type": "frame_ack", "uid": 42, "accepted": true }
```

The `pixels` field is a base64-encoded 675-byte RGB888 payload. Use the binary protocol for high-rate updates.

### `key_frame`

Write the 24 LUMI key colors in key-index order. The `pixels` field contains base64-encoded RGB888 data: exactly 72 bytes (red, green, blue for each key). The daemon applies the connection server's brightness setting and converts the data to the renderer's 48-byte RGB565 heap.

```json
{ "type": "key_frame", "uid": 42, "pixels": "...base64..." }
```

```json
{ "type": "key_frame_ack", "uid": 42, "accepted": true }
```

Key frames require a LUMI device with a reported firmware version of 1.3.0 or newer. Invalid base64, incorrect length, an unsupported device, or an unavailable/older firmware version produces `accepted: false`. The existing 685-byte binary frame format remains dedicated to 15×15 Lightpad grids.

For example, construct a red frame in Python with `base64.b64encode(bytes([255, 0, 0]) * 24).decode("ascii")`.

### `brightness`

Set the LED brightness for a device.

```json
{ "type": "brightness", "uid": 42, "value": 128 }
```

```json
{ "type": "brightness_ack", "uid": 42, "ok": true }
```

Value is clamped to 0-255. Brightness is sticky per-server state, applied to future frame writes before RGB565 conversion. Unix socket and WebSocket servers hold separate brightness settings; changing one does not change the other.

### `subscribe`

Subscribe to real-time event streams.

```json
{ "type": "subscribe", "events": ["device", "touch", "button"] }
```

```json
{ "type": "subscribed", "events": ["button", "device", "touch"] }
```

### `config_get` and `config_set`

Read cached configuration values for a device or request a setting change:

```json
{ "type": "config_get", "uid": 42 }
```

```json
{
  "type": "config_values",
  "uid": 42,
  "values": [{ "item": 10, "value": 50, "min": 0, "max": 100 }]
}
```

```json
{ "type": "config_set", "uid": 42, "item": 10, "value": 50 }
```

```json
{ "type": "config_ack", "uid": 42, "item": 10, "ok": true }
```

The values and ranges above are illustrative; use the device's reported ranges. A successful set response confirms dispatch, not persistence. Subscribe to `config` for subsequent `config_changed` events.

### `topology`

Send `{ "type": "topology" }` to receive `topology_response` with `devices` and `connections` arrays. Each connection contains `device1_uid`, `device2_uid`, `port1`, and `port2`. Subscribe to `topology` for `topology_changed` events with the same arrays.

## Event Stream

Subscribed events are emitted as NDJSON on the Unix socket or JSON text messages on WebSocket. Supported categories are `device`, `touch`, `button`, `config`, and `topology`. A new subscription replaces the previous one on that connection.

### Device Events

```json
{
  "type": "device_added",
  "device": {
    "uid": 42,
    "serial": "LPB1234567890AB",
    "block_type": "lightpad",
    "grid_width": 15,
    "grid_height": 15,
    "battery_level": 85,
    "battery_charging": false,
    "firmware_version": null
  }
}
```

```json
{ "type": "device_removed", "uid": 42 }
```

### Touch Events

```json
{
  "type": "touch",
  "uid": 42,
  "action": "start",
  "index": 0,
  "x": 0.5,
  "y": 0.75,
  "z": 0.8,
  "vx": 0.0,
  "vy": 0.0,
  "vz": 0.0
}
```

Action is one of: `start`, `move`, `end`.

### Button Events

```json
{ "type": "button", "uid": 42, "action": "press" }
```

Action is one of: `press`, `release`. The current API does not expose the protocol button ID.

### Configuration Events

```json
{ "type": "config_changed", "uid": 42, "item": 10, "value": 50 }
```

### Backpressure

Each subscriber has a bounded event queue. If a client stops consuming events and the queue fills, the daemon drops that subscriber rather than blocking the server. Keep event consumers draining continuously.

## Failure Semantics

Frame writes are rejected when:

- The `uid` does not exist
- The payload size is wrong
- The device has not finished entering API mode or has no heap
- The device does not support the requested bitmap or key surface
- A key frame targets unsupported or unavailable LUMI firmware

When in doubt: retry discovery, retry frame writes until accepted, and assume a reconnect invalidates any cached readiness state.
