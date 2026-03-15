"""API servers for blocksd — Unix socket (Hypercolor) and TCP/WebSocket (web UI).

Two server classes share the same TopologyManager:
- **ApiServer** — Unix domain socket, NDJSON + binary frame protocol
- **WebServer** — HTTP static files + WebSocket, same NDJSON message set
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from blocksd.api.events import VALID_EVENTS, EventBroadcaster, _connection_to_dict, _device_to_dict
from blocksd.api.http import http_response, parse_request, serve_static, ws_upgrade_response
from blocksd.api.protocol import (
    BINARY_FRAME_SIZE,
    BINARY_MAGIC,
    PIXEL_DATA_SIZE,
    decode_json,
    encode_json,
    parse_binary_frame,
)
from blocksd.api.websocket import WSOpcode, build_frame, read_frame
from blocksd.led.bitmap import LEDGrid
from blocksd.web import resolve_static_dir

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
        self._manager.on_topology_changed.append(self._broadcaster.broadcast_topology_changed)
        self._manager.on_config_changed.append(self._broadcaster.broadcast_config_changed)

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

        if msg_type == "config_get":
            return self._handle_config_get(msg), None

        if msg_type == "config_set":
            return self._handle_config_set(msg), None

        if msg_type == "topology":
            return self._handle_topology(msg_id), None

        if msg_type == "subscribe":
            valid_events = {event for event in msg.get("events", []) if event in VALID_EVENTS}
            sub_id = self._broadcaster.subscribe(event_queue, valid_events)
            if current_sub_id is not None:
                self._broadcaster.unsubscribe(current_sub_id)
            return {"type": "subscribed", "events": sorted(valid_events)}, sub_id

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

    def _handle_config_get(self, msg: dict[str, Any]) -> dict[str, Any]:
        uid = msg.get("uid")
        msg_id = msg.get("id")
        if uid is None:
            return {"type": "error", "message": "missing uid"}

        values = self._manager.get_config(uid)
        resp: dict[str, Any] = {
            "type": "config_values",
            "uid": uid,
            "values": [
                {"item": cv.item, "value": cv.value, "min": cv.min_val, "max": cv.max_val}
                for cv in values.values()
            ],
        }
        if msg_id:
            resp["id"] = msg_id
        return resp

    def _handle_config_set(self, msg: dict[str, Any]) -> dict[str, Any]:
        uid = msg.get("uid")
        item = msg.get("item")
        value = msg.get("value")
        msg_id = msg.get("id")
        if uid is None or item is None or value is None:
            return {"type": "error", "message": "missing uid/item/value"}

        ok = self._manager.set_config(uid, int(item), int(value))
        resp: dict[str, Any] = {"type": "config_ack", "uid": uid, "item": item, "ok": ok}
        if msg_id:
            resp["id"] = msg_id
        return resp

    def _handle_topology(self, msg_id: str | None) -> dict[str, Any]:
        devices = [_device_to_dict(d) for d in self._manager.devices]
        connections: list[dict[str, Any]] = []
        for group in self._manager.groups:
            connections.extend(_connection_to_dict(c) for c in group.topology.connections)

        resp: dict[str, Any] = {
            "type": "topology_response",
            "devices": devices,
            "connections": connections,
        }
        if msg_id:
            resp["id"] = msg_id
        return resp

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


# ── WebServer (HTTP + WebSocket) ─────────────────────────────────────────────


class WebServer:
    """HTTP static file server + WebSocket API for the web UI.

    Serves the built SPA from a static directory and upgrades ``/ws`` to a
    WebSocket connection using the same NDJSON protocol as the Unix socket API.
    """

    def __init__(
        self,
        manager: TopologyManager,
        host: str = "127.0.0.1",
        port: int = 9010,
        static_dir: Path | None = None,
    ) -> None:
        self._manager = manager
        self._host = host
        self._port = port
        self._static_dir = static_dir or resolve_static_dir()
        self._broadcaster = EventBroadcaster()
        self._server: asyncio.AbstractServer | None = None
        self._start_time = time.monotonic()
        self._brightness_store: dict[int, int] = {}

    async def start(self) -> None:
        """Start the TCP server and wire event broadcasting."""
        self._server = await asyncio.start_server(
            self._handle_connection,
            self._host,
            self._port,
        )

        self._manager.on_device_added.append(self._broadcaster.broadcast_device_added)
        self._manager.on_device_removed.append(self._broadcaster.broadcast_device_removed)
        self._manager.on_touch_event.append(self._broadcaster.broadcast_touch)
        self._manager.on_button_event.append(self._broadcaster.broadcast_button)
        self._manager.on_topology_changed.append(self._broadcaster.broadcast_topology_changed)
        self._manager.on_config_changed.append(self._broadcaster.broadcast_config_changed)

        self._start_time = time.monotonic()
        log.info("Web UI at http://%s:%d", self._host, self._port)

    async def stop(self) -> None:
        """Shut down the TCP server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    # ── HTTP ──────────────────────────────────────────────────────────────

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle one TCP connection — either HTTP or WebSocket upgrade."""
        try:
            request = await asyncio.wait_for(parse_request(reader), timeout=30.0)
            if request is None:
                return

            if request.is_websocket_upgrade and request.path == "/ws":
                log.info("WebSocket client connected")
                writer.write(ws_upgrade_response(request.ws_key))
                await writer.drain()
                await self._handle_websocket(reader, writer)
                log.info("WebSocket client disconnected")
            elif request.method == "GET":
                writer.write(serve_static(request.path, self._static_dir))
                await writer.drain()
            elif request.method == "OPTIONS":
                writer.write(http_response(204, b""))
                await writer.drain()
            else:
                writer.write(http_response(405, b"Method Not Allowed"))
                await writer.drain()
        except (TimeoutError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception:
            log.warning("Web server connection error", exc_info=True)
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    # ── WebSocket ─────────────────────────────────────────────────────────

    async def _handle_websocket(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """WebSocket message loop — same NDJSON protocol as the Unix socket API."""
        event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1024)
        sub_id: int | None = None
        event_task = asyncio.create_task(self._ws_event_writer(writer, event_queue))

        try:
            while True:
                result = await read_frame(reader)
                if result is None:
                    break

                opcode, payload = result

                if opcode == WSOpcode.CLOSE:
                    writer.write(build_frame(WSOpcode.CLOSE, b""))
                    await writer.drain()
                    break

                if opcode == WSOpcode.PING:
                    writer.write(build_frame(WSOpcode.PONG, payload))
                    await writer.drain()
                    continue

                if opcode == WSOpcode.TEXT:
                    try:
                        msg = json.loads(payload)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        self._ws_send(writer, {"type": "error", "message": "malformed JSON"})
                        await writer.drain()
                        continue

                    response, new_sub_id = self._handle_message(msg, event_queue, sub_id)
                    if new_sub_id is not None:
                        sub_id = new_sub_id
                    if response:
                        self._ws_send(writer, response)
                        await writer.drain()

                elif opcode == WSOpcode.BINARY:
                    self._handle_binary_ws(payload)

        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
            pass
        finally:
            event_task.cancel()
            if sub_id is not None:
                self._broadcaster.unsubscribe(sub_id)

    def _ws_send(self, writer: asyncio.StreamWriter, msg: dict[str, Any]) -> None:
        data = json.dumps(msg, separators=(",", ":")).encode()
        writer.write(build_frame(WSOpcode.TEXT, data))

    async def _ws_event_writer(
        self,
        writer: asyncio.StreamWriter,
        queue: asyncio.Queue[dict[str, Any]],
    ) -> None:
        """Drain event queue and send as WebSocket text frames."""
        try:
            while True:
                event = await queue.get()
                self._ws_send(writer, event)
                await writer.drain()
        except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
            pass

    # ── Message handlers ──────────────────────────────────────────────────

    def _handle_message(
        self,
        msg: dict[str, Any],
        event_queue: asyncio.Queue[dict[str, Any]],
        current_sub_id: int | None,
    ) -> tuple[dict[str, Any] | None, int | None]:
        """Dispatch a JSON message — same protocol as the Unix socket API."""
        msg_type = msg.get("type", "")
        msg_id = msg.get("id")

        if msg_type == "ping":
            return self._make_pong(msg_id), None

        if msg_type == "discover":
            return self._make_discover(msg_id), None

        if msg_type == "frame":
            return self._make_frame_ack(msg), None

        if msg_type == "brightness":
            return self._make_brightness_ack(msg), None

        if msg_type == "config_get":
            return self._make_config_values(msg), None

        if msg_type == "config_set":
            return self._make_config_ack(msg), None

        if msg_type == "topology":
            return self._make_topology(msg_id), None

        if msg_type == "subscribe":
            valid_events = {e for e in msg.get("events", []) if e in VALID_EVENTS}
            sub_id = self._broadcaster.subscribe(event_queue, valid_events)
            if current_sub_id is not None:
                self._broadcaster.unsubscribe(current_sub_id)
            return {"type": "subscribed", "events": sorted(valid_events)}, sub_id

        return {"type": "error", "message": f"unknown type: {msg_type}"}, None

    def _make_pong(self, msg_id: str | None) -> dict[str, Any]:
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

    def _make_discover(self, msg_id: str | None) -> dict[str, Any]:
        devices = [_device_to_dict(d) for d in self._manager.devices]
        resp: dict[str, Any] = {"type": "discover_response", "devices": devices}
        if msg_id:
            resp["id"] = msg_id
        return resp

    def _make_topology(self, msg_id: str | None) -> dict[str, Any]:
        devices = [_device_to_dict(d) for d in self._manager.devices]
        connections: list[dict[str, Any]] = []
        for group in self._manager.groups:
            connections.extend(_connection_to_dict(c) for c in group.topology.connections)
        resp: dict[str, Any] = {
            "type": "topology_response",
            "devices": devices,
            "connections": connections,
        }
        if msg_id:
            resp["id"] = msg_id
        return resp

    def _make_config_values(self, msg: dict[str, Any]) -> dict[str, Any]:
        uid = msg.get("uid")
        msg_id = msg.get("id")
        if uid is None:
            return {"type": "error", "message": "missing uid"}
        values = self._manager.get_config(uid)
        resp: dict[str, Any] = {
            "type": "config_values",
            "uid": uid,
            "values": [
                {"item": cv.item, "value": cv.value, "min": cv.min_val, "max": cv.max_val}
                for cv in values.values()
            ],
        }
        if msg_id:
            resp["id"] = msg_id
        return resp

    def _make_config_ack(self, msg: dict[str, Any]) -> dict[str, Any]:
        uid = msg.get("uid")
        item = msg.get("item")
        value = msg.get("value")
        msg_id = msg.get("id")
        if uid is None or item is None or value is None:
            return {"type": "error", "message": "missing uid/item/value"}
        ok = self._manager.set_config(uid, int(item), int(value))
        resp: dict[str, Any] = {"type": "config_ack", "uid": uid, "item": item, "ok": ok}
        if msg_id:
            resp["id"] = msg_id
        return resp

    def _make_frame_ack(self, msg: dict[str, Any]) -> dict[str, Any]:
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

    def _make_brightness_ack(self, msg: dict[str, Any]) -> dict[str, Any]:
        uid = msg.get("uid")
        value = msg.get("value", 255)
        if uid is None:
            return {"type": "brightness_ack", "uid": 0, "ok": False}
        self._brightness_store[uid] = max(0, min(255, value))
        return {"type": "brightness_ack", "uid": uid, "ok": True}

    # ── LED frame ─────────────────────────────────────────────────────────

    def _handle_binary_ws(self, data: bytes) -> None:
        """Process a binary WebSocket frame as an LED frame write."""
        try:
            frame = parse_binary_frame(data)
        except ValueError:
            return
        self._write_rgb888_frame(frame.uid, frame.pixels)

    def _write_rgb888_frame(self, uid: int, pixels: bytes) -> bool:
        """Convert RGB888 → RGB565 and write to device heap."""
        if len(pixels) != PIXEL_DATA_SIZE:
            return False
        device = self._manager.find_device(uid)
        if device is None:
            return False

        brightness = self._brightness_store.get(uid, 255)
        grid = LEDGrid()

        for i in range(225):
            offset = i * 3
            r, g, b = pixels[offset], pixels[offset + 1], pixels[offset + 2]
            if brightness < 255:
                r = (r * brightness) // 255
                g = (g * brightness) // 255
                b = (b * brightness) // 255
            from blocksd.led.bitmap import Color

            grid.set_pixel(i % 15, i // 15, Color(r, g, b))

        return self._manager.set_led_data(uid, grid.heap_data)
