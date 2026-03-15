"""Minimal HTTP/1.1 server — static file serving and WebSocket upgrade.

Not a general-purpose HTTP server. Handles exactly what blocksd needs: serve the
built SPA from a static directory (with SPA fallback) and upgrade ``/ws`` to WebSocket.
"""

from __future__ import annotations

import base64
import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncio
    from pathlib import Path

WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

MIME_TYPES: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".map": "application/json",
    ".txt": "text/plain; charset=utf-8",
    ".wasm": "application/wasm",
}

CORS_HEADERS = "Access-Control-Allow-Origin: *\r\nAccess-Control-Allow-Headers: *\r\n"


class HttpRequest:
    """Parsed HTTP/1.1 request — method, path, and headers."""

    __slots__ = ("headers", "method", "path")

    def __init__(self, method: str, path: str, headers: dict[str, str]) -> None:
        self.method = method
        self.path = path
        self.headers = headers

    @property
    def is_websocket_upgrade(self) -> bool:
        return (
            self.headers.get("upgrade", "").lower() == "websocket"
            and "upgrade" in self.headers.get("connection", "").lower()
        )

    @property
    def ws_key(self) -> str:
        return self.headers.get("sec-websocket-key", "")


async def parse_request(reader: asyncio.StreamReader) -> HttpRequest | None:
    """Parse an HTTP/1.1 request line + headers. Returns None on EOF."""
    line = await reader.readline()
    if not line:
        return None

    parts = line.decode("latin-1").strip().split(" ", 2)
    if len(parts) < 2:
        return None

    method, raw_path = parts[0], parts[1]
    path = raw_path.split("?", 1)[0]  # strip query string

    headers: dict[str, str] = {}
    while True:
        hdr = await reader.readline()
        if hdr in (b"\r\n", b"\n", b""):
            break
        decoded = hdr.decode("latin-1").strip()
        if ":" in decoded:
            k, _, v = decoded.partition(":")
            headers[k.strip().lower()] = v.strip()

    return HttpRequest(method, path, headers)


def ws_upgrade_response(key: str) -> bytes:
    """Build the 101 Switching Protocols response for WebSocket upgrade."""
    accept = base64.b64encode(hashlib.sha1((key + WS_MAGIC).encode()).digest()).decode()
    return (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n"
        "\r\n"
    ).encode()


def http_response(
    status: int,
    body: bytes,
    content_type: str = "text/plain; charset=utf-8",
) -> bytes:
    """Build a minimal HTTP/1.1 response with CORS headers."""
    reason = {200: "OK", 204: "No Content", 404: "Not Found", 405: "Method Not Allowed"}.get(
        status, "Error"
    )
    return (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"{CORS_HEADERS}"
        "Connection: close\r\n"
        "\r\n"
    ).encode() + body


_NOT_BUILT_HTML = (
    b"<html><body style='background:#1a1a2e;color:#e0e0e0;font-family:monospace;padding:2em'>"
    b"<h1>blocksd</h1><p>Web UI not built yet.</p>"
    b"<pre>cd web &amp;&amp; bun install &amp;&amp; bun run build</pre></body></html>"
)


def serve_static(path: str, static_dir: Path) -> bytes:
    """Serve a file from *static_dir* with SPA fallback to ``index.html``."""
    if not static_dir.is_dir():
        return http_response(200, _NOT_BUILT_HTML, "text/html; charset=utf-8")

    clean = path.lstrip("/") or "index.html"
    target = (static_dir / clean).resolve()

    # Path traversal guard
    if not str(target).startswith(str(static_dir.resolve())):
        return http_response(404, b"Not Found")

    if target.is_file():
        mime = MIME_TYPES.get(target.suffix, "application/octet-stream")
        return http_response(200, target.read_bytes(), mime)

    # SPA fallback — serve index.html for client-side routes
    index = static_dir / "index.html"
    if index.is_file():
        return http_response(200, index.read_bytes(), MIME_TYPES[".html"])

    return http_response(404, b"Not Found")
