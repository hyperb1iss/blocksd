# External API

blocksd exposes two APIs for building your own integrations: a Unix domain socket for local IPC (fast, zero overhead) and a WebSocket for browser and network clients. Both speak the same protocol, so code written for one works with the other.

## Connection Methods

### Unix Socket

Low-latency local IPC. This is the preferred method for local integrations.

- Primary path: `$XDG_RUNTIME_DIR/blocksd/blocksd.sock`
- Fallback path: `/tmp/blocksd/blocksd.sock`
- Permissions: directory `0700`, socket `0660`

### WebSocket

Browser and network clients. Used by the web dashboard (`blocksd ui`).

- Default: `ws://localhost:9010/ws`
- Supports both binary LED frames and JSON messages

## Protocol Overview

A single connection can mix two message types:

- **NDJSON**: newline-delimited JSON for control messages and events
- **Binary LED frames**: fixed-size 685-byte packets for LED streaming

The server distinguishes inbound message types by the first byte:

- `0xBD`: binary LED frame
- Anything else: read as newline-delimited JSON

## Recommended Client Strategy

1. Open a control socket
2. Send `discover` to get the device list and `uid` values
3. Only stream LED frames to devices with nonzero `grid_width` and `grid_height`
4. Use the binary frame path (not JSON `frame`) for LED animation
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

Each frame write returns exactly one byte:

| Value  | Meaning  |
| ------ | -------- |
| `0x01` | Accepted |
| `0x00` | Rejected |

`0x00` means the device was unavailable, the `uid` was unknown, or the payload was invalid. Early rejections during device startup are retryable.

### Python Example

```python
import socket
import struct

MAGIC = 0xBD
TYPE_FRAME = 0x01
PIXELS = bytes([255, 0, 0] * 225)  # solid red, 15x15 RGB888
uid = 42

frame = struct.pack("<BBQ", MAGIC, TYPE_FRAME, uid) + PIXELS

with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
    sock.connect("/tmp/blocksd/blocksd.sock")
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
  "version": "0.1.0",
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
      "battery_level": 31,
      "battery_charging": false,
      "firmware_version": ""
    }
  ],
  "id": "req-2"
}
```

The `uid` is a deterministic 64-bit identifier derived from the device serial. Clients can cache it across daemon restarts.

Devices with `grid_width = 0` and `grid_height = 0` do not expose an LED frame surface. Only Lightpad Block and Lightpad Block M advertise non-zero grid dimensions.

::: warning
Discovery is topology-driven, not readiness-driven. A device can appear in `discover_response` before the daemon has finished API mode activation and heap setup. Keep writing frames only after you get an accepted ack.
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

### `brightness`

Set the LED brightness for a device.

```json
{ "type": "brightness", "uid": 42, "value": 128 }
```

```json
{ "type": "brightness_ack", "uid": 42, "ok": true }
```

Value is clamped to 0-255. Brightness is sticky daemon-side state, applied to future frame writes before RGB565 conversion.

### `subscribe`

Subscribe to real-time event streams.

```json
{ "type": "subscribe", "events": ["device", "touch", "button"] }
```

```json
{ "type": "subscribed", "events": ["button", "device", "touch"] }
```

## Event Stream

Subscribed events are emitted as NDJSON on the same socket.

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
    "firmware_version": ""
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
  "touch_index": 0,
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
{ "type": "button", "uid": 42, "button_id": 0, "action": "press" }
```

Action is one of: `press`, `release`.

### Backpressure

Each subscriber has a bounded event queue. If a client stops consuming events and the queue fills, the daemon drops that subscriber rather than blocking the server. Keep event consumers draining continuously.

## Failure Semantics

Frame writes are rejected when:

- The `uid` does not exist
- The payload size is wrong
- The device has not finished entering API/heap-ready state
- The block does not expose LED heap control

When in doubt: retry discovery, retry frame writes until accepted, and assume a reconnect invalidates any cached readiness state.
