"""Sequence renderer execution challenges before publishing pixel frames."""

from __future__ import annotations

import secrets
import time
from typing import TYPE_CHECKING

from blocksd.littlefoot.lifecycle import RENDERER_READY_MARKER
from blocksd.littlefoot.upload import RESPONSE_WARNING_SECONDS, ProgramStatus

if TYPE_CHECKING:
    from blocksd.protocol.remote_heap import RemoteHeap

_QUERY_RETRY_INTERVAL = 0.250
_MAX_NONCE = 0x7FFFFFFF


class LEDProgram:
    """Keep pixels separate until the uploaded renderer answers a fresh challenge.

    Firmware can clear pixels during initialisation. Heap state loss therefore
    restarts the code-only transfer and invalidates every earlier ready reply.
    """

    def __init__(self, heap: RemoteHeap, code: bytes, kind: int, frame_size: int) -> None:
        self.heap = heap
        self.code = code
        self.kind = kind
        self.frame_size = frame_size
        self.ready = False
        self._pixels = bytes(frame_size)
        self._generation = heap.generation
        self._nonce = secrets.randbelow(_MAX_NONCE) + 1
        self._last_query: float | None = None
        self._prepare_upload()

    def _prepare_upload(self) -> None:
        self._started_at = time.monotonic()
        self._first_query: float | None = None
        self.heap.set_bytes(0, bytes(self.heap.size))
        self.heap.set_bytes(0, self.code)

    def _sync_generation(self) -> None:
        if self._generation != self.heap.generation:
            self._generation = self.heap.generation
            self.ready = False
            self._last_query = None
            self._nonce = self._nonce % _MAX_NONCE + 1
            self._prepare_upload()

    def set_frame(self, pixels: bytes | bytearray) -> bool:
        """Accept a complete frame, retaining only the latest during startup."""
        self._sync_generation()
        if len(pixels) != self.frame_size:
            return False
        self._pixels = bytes(pixels)
        if self.ready:
            self.heap.set_bytes(len(self.code), self._pixels)
        return True

    def on_ready(self, message: tuple[int, int, int]) -> None:
        """Publish pixels only for a reply to the current generation's challenge."""
        self._sync_generation()
        if (
            not self.ready
            and self._last_query is not None
            and message == (RENDERER_READY_MARKER, self.kind, self._nonce)
            and not self.heap.is_dirty
            and self.heap.in_flight_count == 0
        ):
            self.ready = True
            self.heap.set_bytes(len(self.code), self._pixels)

    def advance(self, now: float | None = None) -> tuple[int, int, int] | None:
        """Return a readiness challenge after the entire code transfer is ACKed.

        Only an unanswered challenge is retried. Live pixel delivery has no
        query cadence, and unchanged programs can answer after reconnecting.
        """
        self._sync_generation()
        if self.ready or self.heap.is_dirty or self.heap.in_flight_count:
            return None
        if now is None:
            now = time.monotonic()
        if self._last_query is not None and now - self._last_query < _QUERY_RETRY_INTERVAL:
            return None
        self._last_query = now
        if self._first_query is None:
            self._first_query = now
        return (RENDERER_READY_MARKER, self.kind, self._nonce)

    def status(self, now: float | None = None) -> ProgramStatus:
        """Report execution readiness separately from transport acknowledgement."""
        self._sync_generation()
        now = time.monotonic() if now is None else now
        if self.ready:
            state, message = "ready", "Lighting program is responding."
        elif self._first_query is not None:
            state, message = "waiting", "Upload acknowledged; waiting for the lighting program."
            if now - self._first_query >= RESPONSE_WARNING_SECONDS:
                state, message = (
                    "unresponsive",
                    "Upload acknowledged, but the lighting program is not responding.",
                )
        else:
            state, message = "uploading", "Uploading the lighting program."
            if now - self._started_at >= RESPONSE_WARNING_SECONDS:
                state, message = (
                    "unresponsive",
                    "The device has not acknowledged the complete lighting upload.",
                )
        return ProgramStatus(
            "lighting",
            "lighting",
            state,
            message,
            len(self.code),
            int.from_bytes(self.code[8:10], "little"),
        )
