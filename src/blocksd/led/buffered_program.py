"""Present complete bitmap frames while retaining an immutable visible bank."""

from __future__ import annotations

import time

from blocksd.led.program import LEDProgram
from blocksd.littlefoot.bitmap_lifecycle import NOT_READY, PRESENT_BASE, PRESENTED_BASE
from blocksd.littlefoot.lifecycle import RENDERER_READY_MARKER

_PRESENT_RETRY_INTERVAL = 0.250
_MAX_SEQUENCE = 0x7FFFFFFF


class BufferedLEDProgram(LEDProgram):
    """Upload the inactive bank and release the previous bank after its repaint.

    Incoming frames coalesce independently of the submitted frame. Readiness
    establishes bank zero for each new session, including unchanged bytecode
    whose initialise callback does not run again.
    """

    def _prepare_upload(self) -> None:
        super()._prepare_upload()
        self._active_bank = 0
        self._visible = bytes(self.frame_size)
        self._submitted: bytes | None = None
        self._sequence = 0
        self._last_present: float | None = None

    def set_frame(self, pixels: bytes | bytearray) -> bool:
        self._sync_generation()
        if len(pixels) != self.frame_size:
            return False
        self._pixels = bytes(pixels)
        self._queue_frame()
        return True

    def _queue_frame(self) -> None:
        if not self.ready or self._submitted is not None or self._pixels == self._visible:
            return
        if self._sequence == _MAX_SEQUENCE:
            self.heap.reset_device_state()
            self._sync_generation()
            return
        self._sequence += 1
        self._submitted = self._pixels
        self._last_present = None
        offset = len(self.code) + (1 - self._active_bank) * self.frame_size
        self.heap.set_bytes(offset, self._submitted)

    def on_ready(self, message: tuple[int, int, int]) -> None:
        self._sync_generation()
        if not self.ready:
            if (
                self._last_query is not None
                and message == (RENDERER_READY_MARKER, self.kind, self._nonce)
                and not self.heap.is_dirty
                and self.heap.in_flight_count == 0
            ):
                self.ready = True
                self._queue_frame()
            return
        if self._submitted is None or self._last_present is None:
            return
        if message == (NOT_READY, self._nonce, self._sequence):
            self.heap.reset_device_state()
            self._sync_generation()
            return
        bank = 1 - self._active_bank
        if message != (PRESENTED_BASE | bank, self._nonce, self._sequence):
            return
        self._active_bank = bank
        self._visible = self._submitted
        self._submitted = None
        self._last_present = None
        self._queue_frame()

    def advance(self, now: float | None = None) -> tuple[int, int, int] | None:
        self._sync_generation()
        if not self.ready:
            return super().advance(now)
        self._queue_frame()
        if self._submitted is None or self.heap.is_dirty or self.heap.in_flight_count:
            return None
        if now is None:
            now = time.monotonic()
        if self._last_present is not None and now - self._last_present < _PRESENT_RETRY_INTERVAL:
            return None
        self._last_present = now
        return (PRESENT_BASE | (1 - self._active_bank), self._nonce, self._sequence)
