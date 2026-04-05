## blocksd API

Client-facing reference for external integrations such as Hypercolor.

This document describes the daemon socket protocol as it exists in
`src/blocksd/api/` and the LED write path behind it. It is intentionally
practical: exact frame sizes, response shapes, retry expectations, and the
small lifecycle details that matter when you are building an agent or service
against `blocksd`.

### Socket

- Primary path: `$XDG_RUNTIME_DIR/blocksd/blocksd.sock`
- Fallback path: `/tmp/blocksd/blocksd.sock`
- Permissions: the daemon creates the socket directory with `0700` and the
  socket with `0660`

The API is connection-oriented Unix domain sockets. A single connection can mix:

- NDJSON requests and NDJSON event messages
- Fixed-size binary LED frame writes

The server distinguishes inbound message types by the first byte:

- `0xBD` means a binary LED frame
- anything else is read as a newline-delimited JSON message

### Recommended Client Strategy

For robust integrations:

1. Open a control socket.
2. Send `discover` and pick the target device `uid`.
3. Only use the frame stream for devices advertising nonzero `grid_width` and
   `grid_height`.
4. For LED animation, use the binary frame path instead of JSON `frame`.
5. Retry when a frame is rejected immediately after discovery.
6. If you also need events, open a second socket just for `subscribe`.

Why split sockets:

- binary frame writes return a 1-byte ack
- event subscriptions emit NDJSON asynchronously
- sharing one socket is supported, but your client must demultiplex both
  response styles correctly

### Device Lifecycle Notes

Discovery is topology-driven, not "LED-writes-ready"-driven.

That means a device can appear in `discover_response` before the daemon has
fully completed:

- API mode activation
- heap setup
- LED program upload

Practical rule: keep writing frames only after you get an accepted ack.
Early frame rejections are normal during initial connection and should be
treated as retryable, not fatal. Once a device is live, the daemon coalesces
new frames into the latest target state instead of returning a transport-level
"busy" response when the device-side heap writer is saturated.

Capability rule: the daemon only accepts bitmap frame writes for devices that
expose a bitmap LED grid. In the current upstream-compatible model that means
`lightpad` and `lightpad_m`. Devices such as `lumi_keys`, `seaboard`, and the
control blocks are discoverable, but they advertise `grid_width = 0` and
`grid_height = 0`, and frame writes to them will be rejected.

## Binary LED Frames

Use this for streaming, animations, and anything latency-sensitive.

Only send these to devices with nonzero `grid_width` / `grid_height`.

### Frame Layout

Each binary frame is exactly 685 bytes:

| Offset | Size  | Type     | Meaning                         |
| ------ | ----- | -------- | ------------------------------- |
| `0`    | `1`   | `u8`     | magic `0xBD`                    |
| `1`    | `1`   | `u8`     | message type `0x01`             |
| `2`    | `8`   | `u64 LE` | device `uid`                    |
| `10`   | `675` | bytes    | `15 * 15 * 3` RGB888 pixel data |

Constraints:

- `uid` is unsigned 64-bit little-endian
- pixel payload must be exactly 675 bytes
- pixel order is row-major: pixel `i` maps to `x = i % 15`, `y = i // 15`
- each pixel is RGB888 on the wire; the daemon converts to device RGB565

### Binary Ack

Each binary frame write receives exactly one byte back:

- `0x01`: accepted
- `0x00`: rejected

`0x00` means the daemon rejected the write because the device was unavailable,
the `uid` was unknown, or the payload was invalid. Treat early `0x00` results
as retryable while the device is still coming up.

### Binary Example

```python
import socket
import struct

MAGIC = 0xBD
TYPE_FRAME = 0x01
PIXELS = bytes([255, 0, 0] * 225)  # solid red
uid = 42

frame = struct.pack("<BBQ", MAGIC, TYPE_FRAME, uid) + PIXELS

with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
    sock.connect("/tmp/blocksd/blocksd.sock")
    sock.sendall(frame)
    accepted = sock.recv(1) == b"\x01"
    print("accepted:", accepted)
```

## JSON / NDJSON Protocol

JSON messages are newline-delimited UTF-8 JSON objects.

- every request is one line
- every response is one line
- the daemon emits compact JSON without extra spaces

### `ping`

Request:

```json
{ "type": "ping", "id": "req-1" }
```

Response:

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

Request:

```json
{ "type": "discover", "id": "req-2" }
```

Response shape:

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

Notes:

- `uid` is the same value used in binary frames
- `grid_width` / `grid_height` describe the exposed LED/touch surface
- `grid_width = 0` and `grid_height = 0` means the device does not expose a
  bitmap LED frame surface through this API
- discovery means the device is present in topology, not necessarily that the
  first frame will already be accepted
- the `uid` is a deterministic 64-bit identifier derived from the device
  serial, so clients can cache it across daemon restarts

### `frame`

JSON frame writes are supported for compatibility and debugging, but not
recommended for streaming. They carry the same 675 RGB bytes as the binary
protocol, base64-encoded.

Request:

```json
{ "type": "frame", "uid": 42, "pixels": "...base64..." }
```

Response:

```json
{ "type": "frame_ack", "uid": 42, "accepted": true }
```

Rules:

- `pixels` must decode to exactly 675 bytes
- use the binary protocol instead for high-rate updates

### `brightness`

Request:

```json
{ "type": "brightness", "uid": 42, "value": 128 }
```

Response:

```json
{ "type": "brightness_ack", "uid": 42, "ok": true }
```

Rules:

- `value` is clamped to `0..255`
- brightness is sticky daemon-side state per device
- brightness is applied to future frame writes before RGB565 conversion

### `subscribe`

Request:

```json
{ "type": "subscribe", "events": ["device", "touch", "button"] }
```

Response:

```json
{ "type": "subscribed", "events": ["button", "device", "touch"] }
```

Valid event categories:

- `device`
- `touch`
- `button`

Invalid event names are ignored.

## Event Stream

Subscribed event messages are emitted as NDJSON on the same socket.

### Device Events

Added:

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

Removed:

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

`action` is one of:

- `start`
- `move`
- `end`

### Button Events

```json
{ "type": "button", "uid": 42, "button_id": 0, "action": "press" }
```

`action` is one of:

- `press`
- `release`

### Event Backpressure

Each subscribed client has a bounded queue. If the client stops consuming and
the queue fills, the daemon drops that subscriber instead of blocking the whole
server.

Recommendation: keep event consumers draining continuously.

## Hypercolor Integration Notes

If you are building an RGB integration layer:

- use `discover` to build your device map
- keep the `uid` stable in your own cache
- prefer binary writes for every rendered frame
- if you need telemetry, use a second socket for `subscribe`
- coalesce rapid UI updates before sending; the daemon transports full frames,
  not per-pixel deltas from the client API
- on reconnect, treat the device as fresh and re-discover instead of assuming
  the previous socket/session state is still valid

## Failure Semantics

Frame writes are rejected when:

- the `uid` does not exist
- the payload size is wrong
- the device has not finished entering API/heap-ready state yet
- the block does not expose LED heap control

When in doubt:

- retry discovery
- retry frame writes until accepted
- assume a reconnect invalidates any in-memory readiness state
