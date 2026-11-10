"""Validated program binaries and observable upload state."""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from blocksd.littlefoot.assembler import compute_program_checksum

if TYPE_CHECKING:
    from blocksd.protocol.remote_heap import RemoteHeap

RESPONSE_WARNING_SECONDS = 10.0


@dataclass(frozen=True)
class ProgramStatus:
    owner: str = "device"
    name: str | None = None
    state: str = "idle"
    message: str = "Program is managed by the device."
    code_size: int = 0
    heap_size: int = 0


def validate_program(code: bytes, capacity: int) -> int:
    """Check the SDK binary envelope and memory budget before changing a device."""
    if len(code) < 10:
        raise ValueError("Program is missing its LittleFoot header")
    checksum, size, functions, globals_count, heap_size = struct.unpack_from("<5H", code)
    if size != len(code) or checksum != compute_program_checksum(bytearray(code)):
        raise ValueError("Program length or checksum is invalid")
    code_start = 10 + functions * 4
    if not functions or code_start >= size:
        raise ValueError("Program function table is invalid")
    ids: set[int] = set()
    for index in range(functions):
        function_id, address = struct.unpack_from("<HH", code, 10 + index * 4)
        if function_id in ids or not code_start <= address < size:
            raise ValueError("Program contains an invalid or duplicate function")
        ids.add(function_id)
    if size + heap_size > capacity:
        raise ValueError(f"Program needs {size + heap_size} bytes; device has {capacity}")
    # Globals share the SDK's additional 800-byte stack region with call frames.
    if globals_count * 4 + 128 > capacity + 800 - size - heap_size:
        raise ValueError("Program leaves insufficient stack space")
    return heap_size


class ProgramUpload:
    """Custom programs acknowledge transport without claiming execution."""

    def __init__(self, heap: RemoteHeap, code: bytes, name: str) -> None:
        self.heap_size = validate_program(code, heap.size)
        self.heap = heap
        self.code = code
        self.name = name
        self._generation = heap.generation
        self.started_at = time.monotonic()
        self._prepare()

    def _prepare(self) -> None:
        self.heap.set_bytes(0, bytes(self.heap.size))
        self.heap.set_bytes(0, self.code)

    def advance(self) -> None:
        if self._generation != self.heap.generation:
            self._generation = self.heap.generation
            self.started_at = time.monotonic()
            self._prepare()

    def status(self, now: float | None = None) -> ProgramStatus:
        self.advance()
        now = time.monotonic() if now is None else now
        pending = self.heap.is_dirty or self.heap.in_flight_count > 0
        if not pending:
            state, message = "uploaded", "Upload acknowledged; execution is not verified."
        elif now - self.started_at >= RESPONSE_WARNING_SECONDS:
            state, message = "unresponsive", "The device has not acknowledged the complete upload."
        else:
            state, message = "uploading", "Uploading program to the device."
        return ProgramStatus("custom", self.name, state, message, len(self.code), self.heap_size)
