"""Tests for the blocksd API wire protocol."""

from __future__ import annotations

import json

import pytest

from blocksd.api.protocol import (
    BINARY_FRAME_SIZE,
    BINARY_MAGIC,
    BINARY_TYPE_FRAME,
    PIXEL_DATA_SIZE,
    BinaryFrame,
    decode_json,
    encode_json,
    parse_binary_frame,
)


class TestBinaryFrame:
    """Binary frame serialization/deserialization."""

    def test_frame_size_constant(self) -> None:
        assert BINARY_FRAME_SIZE == 685  # 1 magic + 1 type + 8 uid + 675 pixels
        assert PIXEL_DATA_SIZE == 675  # 15 * 15 * 3

    def test_roundtrip_solid_red(self) -> None:
        pixels = bytes([255, 0, 0] * 225)
        frame = BinaryFrame(uid=42, pixels=pixels)
        data = frame.to_bytes()

        assert len(data) == BINARY_FRAME_SIZE
        assert data[0] == BINARY_MAGIC
        assert data[1] == BINARY_TYPE_FRAME

        parsed = parse_binary_frame(data)
        assert parsed.uid == 42
        assert parsed.pixels == pixels

    def test_roundtrip_gradient(self) -> None:
        pixels = bytes(i % 256 for i in range(PIXEL_DATA_SIZE))
        frame = BinaryFrame(uid=0xDEADBEEF, pixels=pixels)
        data = frame.to_bytes()

        parsed = parse_binary_frame(data)
        assert parsed.uid == 0xDEADBEEF
        assert parsed.pixels == pixels

    def test_uid_little_endian(self) -> None:
        frame = BinaryFrame(uid=0x0102030405060708, pixels=b"\x00" * PIXEL_DATA_SIZE)
        data = frame.to_bytes()
        # UID bytes at offsets 2-9, u64 little-endian
        assert data[2] == 0x08
        assert data[3] == 0x07
        assert data[4] == 0x06
        assert data[5] == 0x05
        assert data[6] == 0x04
        assert data[7] == 0x03
        assert data[8] == 0x02
        assert data[9] == 0x01

    def test_parse_too_short(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            parse_binary_frame(b"\xBD\x01\x00\x00")

    def test_parse_bad_magic(self) -> None:
        data = b"\xFF" + b"\x01" + b"\x00" * (BINARY_FRAME_SIZE - 2)
        with pytest.raises(ValueError, match="bad magic"):
            parse_binary_frame(data)

    def test_parse_unknown_type(self) -> None:
        data = bytes([BINARY_MAGIC, 0xFF]) + b"\x00" * (BINARY_FRAME_SIZE - 2)
        with pytest.raises(ValueError, match="unknown binary type"):
            parse_binary_frame(data)

    def test_uid_zero(self) -> None:
        frame = BinaryFrame(uid=0, pixels=b"\x00" * PIXEL_DATA_SIZE)
        parsed = parse_binary_frame(frame.to_bytes())
        assert parsed.uid == 0

    def test_uid_max_u64(self) -> None:
        frame = BinaryFrame(uid=0xFFFFFFFFFFFFFFFF, pixels=b"\x00" * PIXEL_DATA_SIZE)
        parsed = parse_binary_frame(frame.to_bytes())
        assert parsed.uid == 0xFFFFFFFFFFFFFFFF

    def test_uid_real_roli_value(self) -> None:
        """ROLI topology UIDs are 64-bit."""
        uid = 17162900393818307115
        frame = BinaryFrame(uid=uid, pixels=b"\x00" * PIXEL_DATA_SIZE)
        parsed = parse_binary_frame(frame.to_bytes())
        assert parsed.uid == uid


class TestJsonProtocol:
    """NDJSON encoding/decoding."""

    def test_encode_terminates_with_newline(self) -> None:
        data = encode_json({"type": "ping"})
        assert data.endswith(b"\n")

    def test_encode_no_spaces(self) -> None:
        data = encode_json({"type": "pong", "version": "0.1.0"})
        # Compact separators — no spaces after : or ,
        assert b": " not in data
        assert b", " not in data

    def test_roundtrip(self) -> None:
        original = {"type": "discover_response", "devices": [], "id": "req-1"}
        encoded = encode_json(original)
        decoded = decode_json(encoded)
        assert decoded == original

    def test_decode_with_trailing_newline(self) -> None:
        data = b'{"type":"ping"}\n'
        msg = decode_json(data)
        assert msg["type"] == "ping"

    def test_decode_invalid_json(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            decode_json(b"not json at all")

    def test_nested_objects(self) -> None:
        msg = {
            "type": "device_added",
            "device": {
                "uid": 12345,
                "serial": "LPB1234567890AB",
                "block_type": "lightpad",
            },
        }
        decoded = decode_json(encode_json(msg))
        assert decoded["device"]["uid"] == 12345
