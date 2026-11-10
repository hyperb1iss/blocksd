"""Local daemon client used by commands that inspect or control devices."""

from __future__ import annotations

import contextlib
import json
import socket
import sys
import time
from collections import deque
from typing import TYPE_CHECKING, Any, Self

import typer
from websockets.exceptions import WebSocketException
from websockets.sync.client import connect as websocket_connect

from blocksd.config.loader import load_config
from blocksd.paths import default_socket_path

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from pathlib import Path

    from websockets.sync.client import ClientConnection


class ClientError(Exception):
    """An actionable connection or device command failure."""


class DaemonClient:
    """Request/response client that retains events arriving before a response."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        timeout: float = 5.0,
        websocket_url: str | None = None,
    ) -> None:
        from pathlib import Path

        config = load_config()
        configured = config.api_socket
        if sys.platform == "win32":
            if path is not None or configured:
                raise ClientError(
                    "Unix sockets are unavailable on Windows. Remove --socket/api_socket."
                )
            if not config.web_enabled:
                raise ClientError(
                    "Windows commands require web_enabled = true in the daemon config."
                )
            host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(config.web_host, config.web_host)  # noqa: S104
            if ":" in host:
                host = f"[{host}]"
            websocket_url = websocket_url or f"ws://{host}:{config.web_port}/ws"
        if path is not None and websocket_url is not None:
            raise ClientError("Choose a Unix socket or a WebSocket endpoint, not both.")
        self.path = path or (Path(configured) if configured else default_socket_path())
        self.timeout = timeout
        self._websocket_url = websocket_url
        self._websocket: ClientConnection | None = None
        self._socket: socket.socket | None = None
        if sys.platform != "win32" and websocket_url is None:
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._cleanup = contextlib.ExitStack()
        self._buffer = bytearray()
        self._events: deque[dict[str, Any]] = deque()
        self._counter = 0

    def __enter__(self) -> Self:
        try:
            if self._websocket_url:
                self._websocket = self._cleanup.enter_context(
                    websocket_connect(
                        self._websocket_url,
                        proxy=None,
                        compression=None,
                        open_timeout=self.timeout,
                        close_timeout=self.timeout,
                    )
                )
            else:
                assert self._socket is not None
                self._cleanup.enter_context(self._socket)
                self._socket.settimeout(self.timeout)
                self._socket.connect(str(self.path))
        except (OSError, WebSocketException, ValueError) as exc:
            self._cleanup.close()
            raise ClientError(
                f"Cannot reach blocksd at {self._websocket_url or self.path}. Start the service or run 'blocksd run'."
            ) from exc
        return self

    def __exit__(self, *_args: object) -> None:
        self._cleanup.close()

    def _read(self, deadline: float) -> dict[str, Any]:
        if self._websocket is not None:
            try:
                data = self._websocket.recv(timeout=max(0, deadline - time.monotonic()))
            except TimeoutError as exc:
                raise ClientError(
                    "Timed out waiting for the daemon or device confirmation."
                ) from exc
            except (OSError, WebSocketException) as exc:
                raise ClientError(f"Daemon connection failed: {exc}") from exc
            return _decode_message(data)
        assert self._socket is not None
        while b"\n" not in self._buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ClientError("Timed out waiting for the daemon or device confirmation.")
            self._socket.settimeout(remaining)
            try:
                data = self._socket.recv(65536)
            except TimeoutError as exc:
                raise ClientError(
                    "Timed out waiting for the daemon or device confirmation."
                ) from exc
            except OSError as exc:
                raise ClientError(f"Daemon connection failed: {exc}") from exc
            if not data:
                raise ClientError("The daemon closed the connection.")
            self._buffer.extend(data)
        line, _, rest = self._buffer.partition(b"\n")
        self._buffer = bytearray(rest)
        return _decode_message(line)

    def request(self, kind: str, **fields: Any) -> dict[str, Any]:
        self._counter += 1
        request_id = f"cli-{self._counter}"
        data = json.dumps({**fields, "type": kind, "id": request_id})
        try:
            if self._websocket is not None:
                self._websocket.send(data)
            else:
                assert self._socket is not None
                self._socket.sendall(data.encode() + b"\n")
        except (OSError, WebSocketException) as exc:
            raise ClientError(f"Daemon connection failed: {exc}") from exc
        deadline = time.monotonic() + self.timeout
        while True:
            message = self._read(deadline)
            if message.get("id") == request_id:
                if message.get("type") == "error":
                    raise ClientError(str(message.get("message", "Command failed.")))
                return message
            self._events.append(message)

    def wait_for(self, predicate: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout
        while True:
            message = self._events.popleft() if self._events else self._read(deadline)
            if predicate(message):
                return message

    def select_device(self, serial: str | None = None) -> dict[str, Any]:
        devices = self.request("discover")["devices"]
        if serial is not None:
            devices = [device for device in devices if device["serial"] == serial]
        if not devices:
            raise ClientError("No matching device is connected.")
        if len(devices) != 1:
            serials = ", ".join(device["serial"] for device in devices)
            raise ClientError(f"Select one device with --device SERIAL. Connected: {serials}")
        return devices[0]


def _decode_message(data: str | bytes | bytearray) -> dict[str, Any]:
    try:
        message = json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ClientError("The daemon returned an invalid response.") from exc
    if not isinstance(message, dict):
        raise ClientError("The daemon returned an invalid response.")
    return message


@contextlib.contextmanager
def connect(ctx: typer.Context) -> Generator[DaemonClient]:
    """Translate expected command failures into a concise CLI error."""
    try:
        with DaemonClient(ctx.find_root().obj) as client:
            yield client
    except ClientError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
