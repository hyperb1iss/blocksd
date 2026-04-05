"""MIDI connection wrapper for a ROLI Blocks device.

Wraps python-rtmidi input/output pair with asyncio bridging —
rtmidi callbacks arrive on a native thread, we marshal into an asyncio Queue.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rtmidi import MidiIn, MidiOut

log = logging.getLogger(__name__)


class MidiConnection:
    """Bidirectional MIDI SysEx connection to a single ROLI Blocks USB port."""

    def __init__(
        self,
        midi_in: MidiIn,
        midi_out: MidiOut,
        loop: asyncio.AbstractEventLoop,
        *,
        name: str = "",
    ) -> None:
        self._midi_in = midi_in
        self._midi_out = midi_out
        self._loop = loop
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._closed = False
        self.name = name

        # Critical: rtmidi ignores SysEx by default
        self._midi_in.ignore_types(sysex=False, timing=True, active_sense=True)
        self._midi_in.set_callback(self._on_midi_message)

    def _on_midi_message(self, event: tuple[list[int], float], _data: object = None) -> None:
        """rtmidi callback — runs on native thread, marshals to asyncio."""
        message, _delta = event
        if self._closed or not message:
            return
        data = bytes(message)
        with contextlib.suppress(RuntimeError):
            self._loop.call_soon_threadsafe(self._queue.put_nowait, data)

    async def recv(self, timeout: float | None = None) -> bytes | None:  # noqa: ASYNC109
        """Receive next SysEx message, or None on timeout."""
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except TimeoutError:
            return None

    def send(self, data: bytes | bytearray) -> bool:
        """Send a SysEx message to the device."""
        if self._closed or self._midi_out is None:
            return False
        try:
            self._midi_out.send_message(data)
        except Exception:
            log.exception("Failed to send MIDI message")
            return False
        else:
            return True

    def drain(self) -> list[bytes]:
        """Drain all pending messages from the queue (non-blocking)."""
        messages: list[bytes] = []
        while not self._queue.empty():
            try:
                messages.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return messages

    def close(self) -> None:
        """Close both MIDI ports and release ALSA sequencer clients."""
        if self._closed:
            return
        self._closed = True
        with contextlib.suppress(Exception):
            self._midi_in.cancel_callback()
            self._midi_in.close_port()
            self._midi_in.delete()
        with contextlib.suppress(Exception):
            self._midi_out.close_port()
            self._midi_out.delete()
        log.debug("Closed MIDI connection: %s", self.name)

    @property
    def is_open(self) -> bool:
        return not self._closed

    def __repr__(self) -> str:
        state = "open" if self.is_open else "closed"
        return f"MidiConnection({self.name!r}, {state})"


def open_connection(
    input_port: int,
    output_port: int,
    loop: asyncio.AbstractEventLoop,
    *,
    name: str = "",
) -> MidiConnection:
    """Open a MIDI input/output pair and return a MidiConnection."""
    import rtmidi

    midi_in = rtmidi.MidiIn()
    midi_out = rtmidi.MidiOut()

    midi_in.open_port(input_port)
    midi_out.open_port(output_port)

    return MidiConnection(midi_in, midi_out, loop, name=name)
