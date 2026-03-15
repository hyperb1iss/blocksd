"""RFC 6455 WebSocket frame codec for blocksd web server.

Handles frame reading (with client masking), frame building (unmasked, server→client),
and the standard control opcodes (close, ping, pong).
"""

from __future__ import annotations

import asyncio
import struct
from enum import IntEnum


class WSOpcode(IntEnum):
    """WebSocket frame opcodes (RFC 6455 §5.2)."""

    CONTINUATION = 0x0
    TEXT = 0x1
    BINARY = 0x2
    CLOSE = 0x8
    PING = 0x9
    PONG = 0xA


async def read_frame(reader: asyncio.StreamReader) -> tuple[int, bytes] | None:
    """Read one WebSocket frame. Returns ``(opcode, payload)`` or ``None`` on EOF."""
    try:
        header = await reader.readexactly(2)
    except asyncio.IncompleteReadError:
        return None

    opcode = header[0] & 0x0F
    masked = bool(header[1] & 0x80)
    length: int = header[1] & 0x7F

    if length == 126:
        length = struct.unpack("!H", await reader.readexactly(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", await reader.readexactly(8))[0]

    mask_key = await reader.readexactly(4) if masked else None
    payload = await reader.readexactly(length)

    if mask_key:
        payload = _unmask(payload, mask_key)

    return opcode, payload


def build_frame(opcode: int, payload: bytes) -> bytes:
    """Build a server→client WebSocket frame (FIN=1, unmasked)."""
    header = bytearray()
    header.append(0x80 | (opcode & 0x0F))

    length = len(payload)
    if length < 126:
        header.append(length)
    elif length < 65536:
        header.append(126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(127)
        header.extend(struct.pack("!Q", length))

    return bytes(header) + payload


def _unmask(data: bytes, mask: bytes) -> bytes:
    """XOR unmask (RFC 6455 §5.3)."""
    result = bytearray(data)
    for i in range(len(result)):
        result[i] ^= mask[i & 3]
    return bytes(result)
