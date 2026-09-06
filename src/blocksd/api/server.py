"""API servers for blocksd — Unix socket (Hypercolor) and TCP/WebSocket (web UI).

Two server classes share the same TopologyManager:
- **ApiServer** — Unix domain socket, NDJSON + binary frame protocol
- **WebServer** — HTTP static files + WebSocket, same NDJSON message set
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import stat
import sys
import time
from typing import TYPE_CHECKING, Any

from blocksd.api.commands import ApiCommands
from blocksd.api.http import http_response, parse_request, serve_static, ws_upgrade_response
from blocksd.api.protocol import (
    BINARY_FRAME_SIZE,
    BINARY_MAGIC,
    encode_json,
)
from blocksd.api.websocket import WSOpcode, build_frame, read_frame
from blocksd.paths import default_socket_path
from blocksd.web import resolve_static_dir

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine
    from pathlib import Path

    from blocksd.topology.manager import TopologyManager

log = logging.getLogger(__name__)


class _ApiTransport(ApiCommands):
    """Own listeners, accepted connection tasks, and topology subscriptions."""

    def __init__(self, manager: TopologyManager) -> None:
        super().__init__(manager)
        self._server: asyncio.Server | None = None
        self._clients: set[asyncio.Task[None]] = set()
        self._events_attached = False

    def _accept(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        handler: Callable[[asyncio.StreamReader, asyncio.StreamWriter], Coroutine[Any, Any, None]],
    ) -> None:
        if self._server is None or not self._server.is_serving():
            writer.close()
            return
        task = asyncio.create_task(handler(reader, writer))
        self._clients.add(task)
        task.add_done_callback(self._clients.discard)
        task.add_done_callback(lambda _: writer.close())

    def _attach_events(self) -> None:
        self._manager.on_device_added.append(self._broadcaster.broadcast_device_added)
        self._manager.on_device_removed.append(self._broadcaster.broadcast_device_removed)
        self._manager.on_touch_event.append(self._broadcaster.broadcast_touch)
        self._manager.on_button_event.append(self._broadcaster.broadcast_button)
        self._manager.on_topology_changed.append(self._broadcaster.broadcast_topology_changed)
        self._manager.on_config_changed.append(self._broadcaster.broadcast_config_changed)
        self._events_attached = True

    async def stop(self) -> None:
        """Stop accepting work, join all clients, and release callback ownership."""
        if self._server is not None:
            self._server.close()
            self._server.close_clients()
        clients = list(self._clients)
        for task in clients:
            task.cancel()
        await asyncio.gather(*clients, return_exceptions=True)
        if self._server is not None:
            await self._server.wait_closed()
            self._server = None
        if self._events_attached:
            self._manager.on_device_added.remove(self._broadcaster.broadcast_device_added)
            self._manager.on_device_removed.remove(self._broadcaster.broadcast_device_removed)
            self._manager.on_touch_event.remove(self._broadcaster.broadcast_touch)
            self._manager.on_button_event.remove(self._broadcaster.broadcast_button)
            self._manager.on_topology_changed.remove(self._broadcaster.broadcast_topology_changed)
            self._manager.on_config_changed.remove(self._broadcaster.broadcast_config_changed)
            self._events_attached = False


class ApiServer(_ApiTransport):
    """Unix socket API server for external integration.

    Wires into the TopologyManager's callbacks to broadcast device/touch/button
    events to subscribed clients.
    """

    def __init__(
        self,
        manager: TopologyManager,
        socket_path: Path | None = None,
    ) -> None:
        super().__init__(manager)
        self._socket_path = socket_path or default_socket_path()
        self._private_runtime = socket_path is None and sys.platform == "darwin"
        self._start_time = time.monotonic()
        self._client_count = 0
        self._socket_identity: tuple[int, int] | None = None

    async def start(self) -> None:
        """Bind the socket and start accepting connections."""
        if self._server is not None:
            return
        # Ensure socket directory exists
        self._socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self._private_runtime:
            directory = self._socket_path.parent.lstat()
            if (
                not stat.S_ISDIR(directory.st_mode)
                or directory.st_uid != os.getuid()
                or stat.S_IMODE(directory.st_mode) & 0o077
            ):
                raise PermissionError(
                    f"Socket directory must be private and owned by this user: {self._socket_path.parent}"
                )

        # Only reclaim an actual socket whose previous listener is gone.
        if self._socket_path.exists():
            if not stat.S_ISSOCK(self._socket_path.lstat().st_mode):
                raise FileExistsError(f"API socket path is not a socket: {self._socket_path}")
            try:
                _, writer = await asyncio.open_unix_connection(str(self._socket_path))
            except ConnectionRefusedError:
                self._socket_path.unlink()
            else:
                writer.close()
                await writer.wait_closed()
                raise FileExistsError(f"API socket is already active: {self._socket_path}")

        self._server = await asyncio.start_unix_server(
            lambda reader, writer: self._accept(reader, writer, self._handle_client),
            path=str(self._socket_path),
        )

        socket_stat = self._socket_path.stat()
        self._socket_identity = (socket_stat.st_dev, socket_stat.st_ino)
        # Set socket permissions
        os.chmod(self._socket_path, 0o660)

        # Wire up event broadcasting
        self._attach_events()

        self._start_time = time.monotonic()
        log.info("API server listening on %s", self._socket_path)

    async def stop(self) -> None:
        """Shut down the server and clean up the socket."""
        await super().stop()

        if self._socket_identity is not None:
            with contextlib.suppress(FileNotFoundError):
                socket_stat = self._socket_path.lstat()
                if (socket_stat.st_dev, socket_stat.st_ino) == self._socket_identity:
                    self._socket_path.unlink()
            self._socket_identity = None

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
            with contextlib.suppress(asyncio.CancelledError):
                await event_task
            if sub_id is not None:
                self._broadcaster.unsubscribe(sub_id)
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            log.info("Client %d disconnected", client_id)

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


class WebServer(_ApiTransport):
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
        super().__init__(manager)
        self._host = host
        self._port = port
        self._static_dir = static_dir or resolve_static_dir()
        self._start_time = time.monotonic()

    async def start(self) -> None:
        """Start the TCP server and wire event broadcasting."""
        if self._server is not None:
            return
        self._server = await asyncio.start_server(
            lambda reader, writer: self._accept(reader, writer, self._handle_connection),
            self._host,
            self._port,
        )

        self._attach_events()

        self._start_time = time.monotonic()
        log.info("Web UI at http://%s:%d", self._host, self._port)

    async def stop(self) -> None:
        """Shut down the TCP server."""
        await super().stop()

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
                    response, new_sub_id = self._handle_json(payload, event_queue, sub_id)
                    if new_sub_id is not None:
                        sub_id = new_sub_id
                    if response:
                        self._ws_send(writer, response)
                        await writer.drain()

                elif opcode == WSOpcode.BINARY:
                    self._handle_binary_frame(payload)

        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
            pass
        finally:
            event_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await event_task
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
