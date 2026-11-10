"""Compile user programs away from the MIDI event loop, then upload to the same device."""

from __future__ import annotations

import asyncio
import base64
import binascii
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from blocksd.topology.manager import TopologyManager

MAX_SOURCE_BYTES = 256 * 1024


async def load_program(manager: TopologyManager, uid: int, msg: dict[str, Any]) -> None:
    name = msg.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 128 or not name.isprintable():
        raise ValueError("Program name must contain 1 to 128 printable characters")
    if ("source" in msg) == ("code" in msg):
        raise ValueError("Provide either LittleFoot source or compiled code")
    source = msg.get("source")
    includes = msg.get("includes", {})
    if "source" in msg:
        if not isinstance(source, str) or not isinstance(includes, dict):
            raise ValueError("Source must be text and includes must be a filename-to-text object")
        if any(not isinstance(k, str) or not isinstance(v, str) for k, v in includes.items()):
            raise ValueError("Include filenames and contents must be text")
        size = len(source.encode()) + sum(
            len(k.encode()) + len(v.encode()) for k, v in includes.items()
        )
        if size > MAX_SOURCE_BYTES:
            raise ValueError("Source and includes exceed 256 KiB")
    group = manager.program_group(uid)
    heap = group.begin_program_load(uid, name)
    try:
        if isinstance(source, str):
            from blocksd.littlefoot.compiler import compile_source

            code = await asyncio.to_thread(compile_source, source, includes=includes)
        else:
            encoded = msg["code"]
            if not isinstance(encoded, str) or len(encoded) > 10000:
                raise ValueError("Compiled code must be base64 and fit device memory")
            try:
                code = base64.b64decode(encoded, validate=True)
            except binascii.Error as error:
                raise ValueError("Compiled code is not valid base64") from error
        # Compilation yields to disconnect/reconnect and other devices. Never send
        # its result to a replacement session with the same serial number.
        if group not in manager.groups or group.get_heap(uid) is not heap:
            raise ValueError("Device disconnected during compilation; load the program again")
        group.load_program(uid, code, name)
    finally:
        group.cancel_program_load(uid, heap)
