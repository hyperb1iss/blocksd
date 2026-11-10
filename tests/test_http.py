"""Tests for the HTTP parser and static file server."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from blocksd.api.http import (
    HttpRequest,
    http_response,
    parse_request,
    serve_static,
    ws_upgrade_response,
)


class TestParseRequest:
    @pytest.fixture
    async def _reader(self) -> asyncio.StreamReader:
        return asyncio.StreamReader()

    async def test_get_request(self, _reader: asyncio.StreamReader) -> None:
        _reader.feed_data(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        req = await parse_request(_reader)
        assert req is not None
        assert req.method == "GET"
        assert req.path == "/"
        assert req.headers["host"] == "localhost"

    async def test_websocket_upgrade(self, _reader: asyncio.StreamReader) -> None:
        _reader.feed_data(
            b"GET /ws HTTP/1.1\r\n"
            b"Upgrade: websocket\r\n"
            b"Connection: Upgrade\r\n"
            b"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
            b"\r\n"
        )
        req = await parse_request(_reader)
        assert req is not None
        assert req.is_websocket_upgrade
        assert req.path == "/ws"
        assert req.ws_key == "dGhlIHNhbXBsZSBub25jZQ=="

    async def test_eof_returns_none(self, _reader: asyncio.StreamReader) -> None:
        _reader.feed_data(b"")
        _reader.feed_eof()
        req = await parse_request(_reader)
        assert req is None

    async def test_strips_query_string(self, _reader: asyncio.StreamReader) -> None:
        _reader.feed_data(b"GET /page?q=test HTTP/1.1\r\n\r\n")
        req = await parse_request(_reader)
        assert req is not None
        assert req.path == "/page"


class TestWsUpgrade:
    def test_rfc_vector(self) -> None:
        """Verify WebSocket accept key computation."""
        resp = ws_upgrade_response("dGhlIHNhbXBsZSBub25jZQ==")
        assert b"101 Switching Protocols" in resp
        assert b"Sec-WebSocket-Accept: " in resp
        # Verified with Python hashlib, Node.js crypto, and sha1sum
        assert b"s3pPLMBiTxaQ9kYGzzhZRbK+xOo=" in resp


class TestHttpResponse:
    def test_200_response(self) -> None:
        resp = http_response(200, b"OK")
        assert resp.startswith(b"HTTP/1.1 200 OK\r\n")
        assert b"Content-Length: 2" in resp
        assert resp.endswith(b"\r\nOK")

    def test_404_response(self) -> None:
        resp = http_response(404, b"Not Found")
        assert b"404 Not Found" in resp


class TestServeStatic:
    def test_serves_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "test.js").write_text("console.log('hi')")
            resp = serve_static("/test.js", path)
            assert b"200 OK" in resp
            assert b"application/javascript" in resp
            assert b"console.log('hi')" in resp

    def test_index_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "index.html").write_text("<html></html>")
            resp = serve_static("/some/route", path)
            assert b"200 OK" in resp
            assert b"<html></html>" in resp

    def test_path_traversal_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "index.html").write_text("safe")
            resp = serve_static("/../../../etc/passwd", path)
            assert b"404" in resp

    def test_no_static_dir(self) -> None:
        resp = serve_static("/", Path("/nonexistent/path"))
        assert b"200 OK" in resp
        assert b"not built" in resp.lower()

    def test_correct_mime_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            (path / "style.css").write_text("body{}")
            resp = serve_static("/style.css", path)
            assert b"text/css" in resp


class TestHttpRequest:
    def test_non_ws_request(self) -> None:
        req = HttpRequest("GET", "/", {"host": "localhost"})
        assert not req.is_websocket_upgrade


@pytest.mark.parametrize(
    ("origin", "host", "allowed"),
    [
        ("http://localhost:9010", "localhost:9010", True),
        ("http://127.0.0.1:9010", "127.0.0.1:9010", True),
        ("http://[::1]:9010", "[::1]:9010", True),
        ("http://localhost:5173", "localhost:5173", True),
        ("https://untrusted.example", "localhost:9010", False),
        ("null", "localhost:9010", False),
        ("http://localhost:9011", "localhost:9010", False),
        ("http://rebound.example:9010", "rebound.example:9010", False),
        ("http://user@localhost:9010", "user@localhost:9010", False),
        (None, "localhost:9010", True),
    ],
)
def test_browser_origin(origin, host, allowed):
    from blocksd.api.http import websocket_origin_allowed

    headers = {"host": host}
    if origin is not None:
        headers["origin"] = origin
    assert websocket_origin_allowed(HttpRequest("GET", "/ws", headers), "127.0.0.1") is allowed


@pytest.mark.parametrize(
    ("bound_host", "host", "allowed"),
    [
        ("127.0.1.1", "rebound.example:9010", False),
        ("127.0.1.1", "127.0.1.1:9010", True),
        ("0.0.0.0", "rebound.example:9010", False),  # noqa: S104 - no socket is bound
        ("::", "rebound.example:9010", False),
        ("192.168.1.10", "rebound.example:9010", False),
        ("0.0.0.0", "192.168.1.10:9010", True),  # noqa: S104 - no socket is bound
        ("::", "[fe80::1]:9010", True),
        ("studio.local", "studio.local:9010", True),
        ("studio.local", "rebound.example:9010", False),
    ],
)
def test_browser_origin_with_custom_bindings(bound_host, host, allowed):
    from blocksd.api.http import websocket_origin_allowed

    request = HttpRequest("GET", "/ws", {"host": host, "origin": f"http://{host}"})
    assert websocket_origin_allowed(request, bound_host) is allowed


@pytest.mark.parametrize(
    "path",
    [
        r"\\host\share\x",
        "//host/share/x",
        r"C:\secret",
        "C:/secret",
        "/C:/secret",
        "/index.html:stream",
    ],
)
def test_windows_paths_are_rejected_before_filesystem_resolution(path, monkeypatch, tmp_path):
    from unittest.mock import Mock

    resolve = Mock(side_effect=AssertionError("request reached filesystem resolution"))
    monkeypatch.setattr(Path, "resolve", resolve)
    assert b"404 Not Found" in serve_static(path, tmp_path)
    resolve.assert_not_called()


def test_static_sibling_with_same_prefix_is_not_served(tmp_path):
    static = tmp_path / "web"
    sibling = tmp_path / "web-private"
    static.mkdir()
    sibling.mkdir()
    (sibling / "secret.txt").write_text("private")
    response = serve_static("/../web-private/secret.txt", static)
    assert b"404 Not Found" in response
    assert b"private" not in response
