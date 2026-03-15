"""Integration tests for the WebServer — HTTP + WebSocket end-to-end."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import struct

import pytest

from blocksd.api.server import WebServer
from blocksd.topology.manager import TopologyManager


def _ws_magic_accept(key: str) -> str:
    magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    return base64.b64encode(hashlib.sha1((key + magic).encode()).digest()).decode()


def _build_masked_frame(opcode: int, payload: bytes) -> bytes:
    """Build a client→server (masked) WebSocket frame."""
    mask = os.urandom(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    header = bytearray()
    header.append(0x80 | opcode)
    length = len(payload)
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", length))
    header.extend(mask)
    return bytes(header) + masked


def _parse_ws_frame(data: bytes) -> tuple[int, bytes]:
    """Parse a server→client (unmasked) WebSocket frame from raw bytes."""
    opcode = data[0] & 0x0F
    length = data[1] & 0x7F
    offset = 2
    if length == 126:
        length = struct.unpack("!H", data[2:4])[0]
        offset = 4
    elif length == 127:
        length = struct.unpack("!Q", data[2:10])[0]
        offset = 10
    return opcode, data[offset : offset + length]


class TestWebServerIntegration:
    """Full TCP-level tests — connect, upgrade, exchange WebSocket messages."""

    @pytest.fixture
    async def server(self) -> WebServer:
        manager = TopologyManager()
        srv = WebServer(manager, host="127.0.0.1", port=0)
        await srv.start()
        yield srv
        await srv.stop()

    def _get_port(self, server: WebServer) -> int:
        sockets = server._server.sockets  # type: ignore[union-attr]
        return sockets[0].getsockname()[1]

    async def test_http_serves_index(self, server: WebServer) -> None:
        """GET / returns 200 with HTML content."""
        port = self._get_port(server)
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()
        response = await reader.read(4096)
        writer.close()
        assert b"200 OK" in response
        assert b"text/html" in response

    async def test_websocket_handshake(self, server: WebServer) -> None:
        """WebSocket upgrade completes with valid Sec-WebSocket-Accept."""
        port = self._get_port(server)
        reader, writer = await asyncio.open_connection("127.0.0.1", port)

        key = base64.b64encode(os.urandom(16)).decode()
        writer.write(
            f"GET /ws HTTP/1.1\r\n"
            f"Host: localhost:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n".encode()
        )
        await writer.drain()

        response = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5.0)
        assert b"101 Switching Protocols" in response
        assert _ws_magic_accept(key).encode() in response

        writer.close()

    async def test_websocket_ping_pong(self, server: WebServer) -> None:
        """Send a JSON ping over WebSocket, receive pong."""
        port = self._get_port(server)
        reader, writer = await asyncio.open_connection("127.0.0.1", port)

        # Upgrade
        key = base64.b64encode(os.urandom(16)).decode()
        writer.write(
            f"GET /ws HTTP/1.1\r\n"
            f"Host: localhost:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n".encode()
        )
        await writer.drain()
        await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5.0)

        # Send ping message
        ping = json.dumps({"type": "ping", "id": "t1"}).encode()
        writer.write(_build_masked_frame(0x1, ping))
        await writer.drain()

        # Read pong response
        raw = await asyncio.wait_for(reader.read(4096), timeout=5.0)
        opcode, payload = _parse_ws_frame(raw)
        assert opcode == 0x1  # TEXT
        msg = json.loads(payload)
        assert msg["type"] == "pong"
        assert msg["id"] == "t1"
        assert "uptime_seconds" in msg

        writer.close()

    async def test_websocket_subscribe_and_discover(self, server: WebServer) -> None:
        """Subscribe to events and discover devices."""
        port = self._get_port(server)
        reader, writer = await asyncio.open_connection("127.0.0.1", port)

        # Upgrade
        key = base64.b64encode(os.urandom(16)).decode()
        writer.write(
            f"GET /ws HTTP/1.1\r\n"
            f"Host: localhost:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n".encode()
        )
        await writer.drain()
        await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5.0)

        # Subscribe
        sub = json.dumps({"type": "subscribe", "events": ["device"]}).encode()
        writer.write(_build_masked_frame(0x1, sub))
        await writer.drain()

        raw = await asyncio.wait_for(reader.read(4096), timeout=5.0)
        _, payload = _parse_ws_frame(raw)
        msg = json.loads(payload)
        assert msg["type"] == "subscribed"
        assert "device" in msg["events"]

        # Discover (no devices)
        disc = json.dumps({"type": "discover"}).encode()
        writer.write(_build_masked_frame(0x1, disc))
        await writer.drain()

        raw = await asyncio.wait_for(reader.read(4096), timeout=5.0)
        _, payload = _parse_ws_frame(raw)
        msg = json.loads(payload)
        assert msg["type"] == "discover_response"
        assert msg["devices"] == []

        writer.close()

    async def test_websocket_topology(self, server: WebServer) -> None:
        """Request topology over WebSocket."""
        port = self._get_port(server)
        reader, writer = await asyncio.open_connection("127.0.0.1", port)

        # Upgrade
        key = base64.b64encode(os.urandom(16)).decode()
        writer.write(
            f"GET /ws HTTP/1.1\r\n"
            f"Host: localhost:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n".encode()
        )
        await writer.drain()
        await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5.0)

        # Request topology
        topo = json.dumps({"type": "topology", "id": "t2"}).encode()
        writer.write(_build_masked_frame(0x1, topo))
        await writer.drain()

        raw = await asyncio.wait_for(reader.read(4096), timeout=5.0)
        _, payload = _parse_ws_frame(raw)
        msg = json.loads(payload)
        assert msg["type"] == "topology_response"
        assert msg["id"] == "t2"
        assert isinstance(msg["devices"], list)
        assert isinstance(msg["connections"], list)

        writer.close()
