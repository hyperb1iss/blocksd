"""Tests for the WebSocket frame codec."""

import asyncio

import pytest

from blocksd.api.websocket import WSOpcode, build_frame, read_frame


def _make_masked_frame(opcode: int, payload: bytes) -> bytes:
    """Build a client→server masked frame for testing."""
    import os

    mask = os.urandom(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))

    header = bytearray()
    header.append(0x80 | opcode)  # FIN=1

    length = len(payload)
    if length < 126:
        header.append(0x80 | length)  # MASK=1
    elif length < 65536:
        header.append(0x80 | 126)
        header.extend(length.to_bytes(2, "big"))
    else:
        header.append(0x80 | 127)
        header.extend(length.to_bytes(8, "big"))

    header.extend(mask)
    return bytes(header) + masked


class TestBuildFrame:
    def test_small_text_frame(self) -> None:
        frame = build_frame(WSOpcode.TEXT, b"hello")
        assert frame[0] == 0x81  # FIN + TEXT
        assert frame[1] == 5  # length, no mask
        assert frame[2:] == b"hello"

    def test_empty_close_frame(self) -> None:
        frame = build_frame(WSOpcode.CLOSE, b"")
        assert frame[0] == 0x88
        assert frame[1] == 0

    def test_medium_payload(self) -> None:
        payload = b"x" * 200
        frame = build_frame(WSOpcode.BINARY, payload)
        assert frame[0] == 0x82  # FIN + BINARY
        assert frame[1] == 126  # extended length marker
        assert int.from_bytes(frame[2:4], "big") == 200
        assert frame[4:] == payload

    def test_large_payload(self) -> None:
        payload = b"y" * 70000
        frame = build_frame(WSOpcode.BINARY, payload)
        assert frame[1] == 127  # 64-bit length marker
        assert int.from_bytes(frame[2:10], "big") == 70000
        assert frame[10:] == payload


class TestReadFrame:
    @pytest.fixture
    def _reader(self) -> asyncio.StreamReader:
        return asyncio.StreamReader()

    async def test_read_masked_text(self, _reader: asyncio.StreamReader) -> None:
        wire = _make_masked_frame(WSOpcode.TEXT, b'{"type":"ping"}')
        _reader.feed_data(wire)
        result = await read_frame(_reader)
        assert result is not None
        opcode, payload = result
        assert opcode == WSOpcode.TEXT
        assert payload == b'{"type":"ping"}'

    async def test_read_close(self, _reader: asyncio.StreamReader) -> None:
        wire = _make_masked_frame(WSOpcode.CLOSE, b"")
        _reader.feed_data(wire)
        result = await read_frame(_reader)
        assert result is not None
        assert result[0] == WSOpcode.CLOSE

    async def test_eof_returns_none(self, _reader: asyncio.StreamReader) -> None:
        _reader.feed_eof()
        result = await read_frame(_reader)
        assert result is None

    async def test_read_medium_masked(self, _reader: asyncio.StreamReader) -> None:
        payload = b"A" * 200
        wire = _make_masked_frame(WSOpcode.BINARY, payload)
        _reader.feed_data(wire)
        result = await read_frame(_reader)
        assert result is not None
        assert result[1] == payload


class TestRoundTrip:
    async def test_unmasked_read(self) -> None:
        """Server frames are unmasked — verify we can read them back."""
        reader = asyncio.StreamReader()
        payload = b'{"type":"pong"}'
        frame = build_frame(WSOpcode.TEXT, payload)
        reader.feed_data(frame)
        result = await read_frame(reader)
        assert result is not None
        assert result[1] == payload
