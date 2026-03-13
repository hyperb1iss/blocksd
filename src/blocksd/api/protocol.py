"""Wire protocol — NDJSON + binary frame parser/serializer.

Two message formats coexist on the same socket:

- **JSON:** newline-delimited JSON objects (first byte is `{` = 0x7B)
- **Binary:** fixed-size frame writes (first byte is magic 0xBD)

The server peeks at the first byte to dispatch to the correct parser.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from typing import Any

# Binary frame constants
BINARY_MAGIC = 0xBD
BINARY_TYPE_FRAME = 0x01
BINARY_FRAME_SIZE = 681  # 1 magic + 1 type + 4 uid + 675 pixels
BINARY_HEADER = struct.Struct("<BBL")  # magic, type, uid (little-endian)
PIXEL_DATA_SIZE = 675  # 15 * 15 * 3 bytes (RGB888)


@dataclass(frozen=True, slots=True)
class BinaryFrame:
    """A binary frame write message."""

    uid: int
    pixels: bytes  # 675 bytes of RGB888

    def to_bytes(self) -> bytes:
        return BINARY_HEADER.pack(BINARY_MAGIC, BINARY_TYPE_FRAME, self.uid) + self.pixels


def parse_binary_frame(data: bytes) -> BinaryFrame:
    """Parse a 681-byte binary frame message.

    Raises ValueError if the data is malformed.
    """
    if len(data) < BINARY_FRAME_SIZE:
        raise ValueError(f"binary frame too short: {len(data)} < {BINARY_FRAME_SIZE}")

    magic, msg_type, uid = BINARY_HEADER.unpack_from(data)
    if magic != BINARY_MAGIC:
        raise ValueError(f"bad magic: 0x{magic:02X}")
    if msg_type != BINARY_TYPE_FRAME:
        raise ValueError(f"unknown binary type: 0x{msg_type:02X}")

    pixels = data[BINARY_HEADER.size : BINARY_HEADER.size + PIXEL_DATA_SIZE]
    return BinaryFrame(uid=uid, pixels=pixels)


def encode_json(msg: dict[str, Any]) -> bytes:
    """Encode a JSON message as NDJSON (newline-terminated)."""
    return json.dumps(msg, separators=(",", ":")).encode() + b"\n"


def decode_json(line: bytes) -> dict[str, Any]:
    """Decode a single NDJSON line."""
    return json.loads(line)
