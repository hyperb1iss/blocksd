"""Unix socket API server for blocksd.

Accepts connections from Hypercolor and other clients over a Unix domain socket.
Supports both NDJSON (request/response) and binary (frame writes) protocols on
the same connection, disambiguated by peeking at the first byte.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from blocksd.api.events import EventBroadcaster
from blocksd.api.protocol import (
    BINARY_FRAME_SIZE,
    BINARY_MAGIC,
    PIXEL_DATA_SIZE,
    decode_json,
    encode_json,
    parse_binary_frame,
)
from blocksd.led.bitmap import LEDGrid

if TYPE_CHECKING:
    from blocksd.topology.manager import TopologyManager

log = logging.getLogger(__name__)

VERSION = "0.1.0"


def default_socket_path() -> Path:
    """Default socket path: $XDG_RUNTIME_DIR/blocksd/blocksd.sock."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "blocksd" / "blocksd.sock"
    return Path("/tmp/blocksd/blocksd.sock")


class ApiServer:
    """Unix socket API server for external integration.

    Wires into the TopologyManager's callbacks to broadcast device/touch/button
    events to subscribed clients.
    """

    def __init__(
        self,
        manager: TopologyManager,
        socket_path: Path | None = None,
    ) -> None:
        self._manager = manager
        self._socket_path = socket_path or default_socket_path()
        self._broadcaster = EventBroadcaster()
        self._server: asyncio.AbstractServer | None = None
        self._start_time = time.monotonic()
        self._client_count = 0

    async def start(self) -> None:
        """Bind the socket and start accepting connections."""
        # Ensure socket directory exists
        self._socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        # Remove stale socket
        if self._socket_path.exists():
            self._socket_path.unlink()

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self._socket_path),
        )

        # Set socket permissions
        os.chmod(self._socket_path, 0o660)

        # Wire up event broadcasting
        self._manager.on_device_added.append(self._broadcaster.broadcast_device_added)
        self._manager.on_device_removed.append(self._broadcaster.broadcast_device_removed)
        self._manager.on_touch_event.append(self._broadcaster.broadcast_touch)
        self._manager.on_button_event.append(self._broadcaster.broadcast_button)

        self._start_time = time.monotonic()
        log.info("API server listening on %s", self._socket_path)

    async def stop(self) -> None:
        """Shut down the server and clean up the socket."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        if self._socket_path.exists():
            self._socket_path.unlink()

        log.info("API server stopped")

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a single client connection."""
        self._client_count += 1
        client_id = self._client_count
        log.info("Client %d connected", client_id)

        # Event queue for this client's subscriptions
        event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1024)
        sub_id: int | None = None

        # Start event writer task
        event_task = asyncio.create_task(
            self._event_writer(writer, event_queue),
            name=f"api-events:{client_id}",
        )

        try:
            while True:
                # Peek at first byte to determine message type
                first_byte = await reader.read(1)
                if not first_byte:
                    break  # EOF

                if first_byte[0] == BINARY_MAGIC:
                    # Binary frame — read remaining bytes
                    remaining = await reader.readexactly(BINARY_FRAME_SIZE - 1)
                    data = first_byte + remaining
                    accepted = self._handle_binary_frame(data)
                    writer.write(b"\x01" if accepted else b"\x00")
                    await writer.drain()
                else:
                    # JSON — read until newline
                    rest = await reader.readline()
                    if not rest:
                        break
                    line = first_byte + rest
                    response, new_sub_id = self._handle_json(line, event_queue, sub_id)
                    if new_sub_id is not None:
                        sub_id = new_sub_id
                    if response:
                        writer.write(encode_json(response))
                        await writer.drain()

        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception:
            log.exception("Client %d error", client_id)
        finally:
            event_task.cancel()
            if sub_id is not None:
                self._broadcaster.unsubscribe(sub_id)
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            log.info("Client %d disconnected", client_id)

    def _handle_binary_frame(self, data: bytes) -> bool:
        """Process a binary frame write. Returns True if accepted."""
        try:
            frame = parse_binary_frame(data)
        except ValueError:
            log.debug("Malformed binary frame")
            return False

        return self._write_rgb888_frame(frame.uid, frame.pixels)

    def _handle_json(
        self,
        line: bytes,
        event_queue: asyncio.Queue[dict[str, Any]],
        current_sub_id: int | None,
    ) -> tuple[dict[str, Any] | None, int | None]:
        """Process a JSON request. Returns (response, new_sub_id_or_None)."""
        try:
            msg = decode_json(line)
        except Exception:
            return {"type": "error", "message": "malformed JSON"}, None

        msg_type = msg.get("type", "")
        msg_id = msg.get("id")

        if msg_type == "ping":
            return self._handle_ping(msg_id), None

        if msg_type == "discover":
            return self._handle_discover(msg_id), None

        if msg_type == "frame":
            return self._handle_json_frame(msg), None

        if msg_type == "brightness":
            return self._handle_brightness(msg), None

        if msg_type == "subscribe":
            events = set(msg.get("events", []))
            sub_id = self._broadcaster.subscribe(event_queue, events)
            if current_sub_id is not None:
                self._broadcaster.unsubscribe(current_sub_id)
            return {"type": "subscribed", "events": sorted(events)}, sub_id

        return {"type": "error", "message": f"unknown type: {msg_type}"}, None

    def _handle_ping(self, msg_id: str | None) -> dict[str, Any]:
        uptime = time.monotonic() - self._start_time
        resp: dict[str, Any] = {
            "type": "pong",
            "version": VERSION,
            "uptime_seconds": int(uptime),
            "device_count": len(self._manager.devices),
        }
        if msg_id:
            resp["id"] = msg_id
        return resp

    def _handle_discover(self, msg_id: str | None) -> dict[str, Any]:
        from blocksd.api.events import _device_to_dict

        devices = [_device_to_dict(d) for d in self._manager.devices]
        resp: dict[str, Any] = {
            "type": "discover_response",
            "devices": devices,
        }
        if msg_id:
            resp["id"] = msg_id
        return resp

    def _handle_json_frame(self, msg: dict[str, Any]) -> dict[str, Any]:
        uid = msg.get("uid")
        pixels_b64 = msg.get("pixels", "")
        if uid is None:
            return {"type": "frame_ack", "uid": 0, "accepted": False}

        try:
            pixels = base64.b64decode(pixels_b64)
        except Exception:
            return {"type": "frame_ack", "uid": uid, "accepted": False}

        accepted = self._write_rgb888_frame(uid, pixels)
        return {"type": "frame_ack", "uid": uid, "accepted": accepted}

    def _handle_brightness(self, msg: dict[str, Any]) -> dict[str, Any]:
        uid = msg.get("uid")
        value = msg.get("value", 255)
        if uid is None:
            return {"type": "brightness_ack", "uid": 0, "ok": False}

        # Store brightness per device for future frame scaling
        # For now, brightness is applied by scaling RGB values in _write_rgb888_frame
        self._brightness_map[uid] = max(0, min(255, value))
        return {"type": "brightness_ack", "uid": uid, "ok": True}

    @property
    def _brightness_map(self) -> dict[int, int]:
        if not hasattr(self, "_brightness_store"):
            self._brightness_store: dict[int, int] = {}
        return self._brightness_store

    def _write_rgb888_frame(self, uid: int, pixels: bytes) -> bool:
        """Convert RGB888 frame to RGB565 and write to device heap."""
        if len(pixels) != PIXEL_DATA_SIZE:
            return False

        device = self._manager.find_device(uid)
        if device is None:
            return False

        brightness = self._brightness_map.get(uid, 255)
        grid = LEDGrid()

        for i in range(225):
            offset = i * 3
            r, g, b = pixels[offset], pixels[offset + 1], pixels[offset + 2]

            # Apply brightness scaling
            if brightness < 255:
                r = (r * brightness) // 255
                g = (g * brightness) // 255
                b = (b * brightness) // 255

            x = i % 15
            y = i // 15
            from blocksd.led.bitmap import Color
            grid.set_pixel(x, y, Color(r, g, b))

        return self._manager.set_led_data(uid, grid.heap_data)

    @staticmethod
    async def _event_writer(
        writer: asyncio.StreamWriter,
        queue: asyncio.Queue[dict[str, Any]],
    ) -> None:
        """Drain event queue and write to client."""
        try:
            while True:
                event = await queue.get()
                writer.write(encode_json(event))
                await writer.drain()
        except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
            pass
