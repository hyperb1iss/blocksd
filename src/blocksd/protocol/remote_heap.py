"""RemoteHeap — stateful heap manager with ACK tracking and retransmission.

Ported from roli_LittleFootRemoteHeap.h.

Tracks the difference between confirmed device state and desired target state.
Generates SharedDataChange packets to synchronize, using optimistic diffing
against in-flight message results and automatic retransmission on ACK timeout.

The device heap holds program bytecode + heap data. For LED control,
BitmapLEDProgram reads RGB565 pixel data starting at the program size offset.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

from blocksd.protocol.builder import HostPacketBuilder
from blocksd.protocol.data_change import (
    DataChangeEncoder,
    compute_diff,
    encode_regions,
)

# Unknown byte sentinel — device state not yet confirmed
_UNKNOWN: int = 0x100

# Retransmit oldest in-flight message after this many seconds
RETRANSMIT_TIMEOUT: float = 0.250

# Max total payload bytes allowed in-flight before blocking new sends
MAX_IN_FLIGHT_BYTES: int = 200

# Max SysEx packet payload for data change messages
MAX_PACKET_BYTES: int = 200

# 10-bit packet counter mask (ACKs reference this range)
_COUNTER_MASK: int = 0x3FF


@dataclass(slots=True)
class _InFlightMessage:
    """A data change packet awaiting ACK from the device."""

    packet_index: int
    packet_data: bytes
    result_state: bytearray
    payload_size: int
    last_send_time: float


class RemoteHeap:
    """Manages device heap state with diff-based updates and ACK tracking.

    Mirrors C++ LittleFootRemoteHeap: confirmed device state uses uint16
    per byte (0x100 = unknown sentinel). Diffs against the optimistic
    expected state (tail of in-flight queue), generates SharedDataChange
    packets, and handles ACK-driven confirmation with retransmission.
    """

    def __init__(self, size: int) -> None:
        self._size = size
        self._device_state: list[int] = [_UNKNOWN] * size
        self._target = bytearray(size)
        self._messages: deque[_InFlightMessage] = deque()
        self._packet_index: int = 0

    @property
    def size(self) -> int:
        return self._size

    @property
    def is_dirty(self) -> bool:
        """True if target differs from expected device state."""
        return self._expected_state() != self._target

    @property
    def in_flight_count(self) -> int:
        return len(self._messages)

    @property
    def in_flight_bytes(self) -> int:
        return sum(m.payload_size for m in self._messages)

    @property
    def target(self) -> bytes:
        return bytes(self._target)

    @property
    def packet_index(self) -> int:
        return self._packet_index

    def reset(self) -> None:
        """Reset all state — device becomes unknown, target zeroed."""
        self._device_state = [_UNKNOWN] * self._size
        self._target = bytearray(self._size)
        self._messages.clear()
        self._packet_index = 0

    def reset_device_state(self) -> None:
        """Mark all device bytes as unknown (e.g., after reconnect).

        Clears in-flight messages since they'll never be ACK'd.
        """
        self._device_state = [_UNKNOWN] * self._size
        self._messages.clear()

    def set_bytes(self, offset: int, data: bytes | bytearray) -> None:
        """Update target heap at offset."""
        end = offset + len(data)
        if end > self._size:
            raise ValueError(
                f"Write past heap end: offset={offset}, len={len(data)}, heap={self._size}"
            )
        self._target[offset:end] = data

    def send_changes(self, device_index: int, now: float | None = None) -> bytes | None:
        """Generate a SharedDataChange packet if target differs from expected state.

        Returns the SysEx bytes to send, or None if no changes needed
        or the in-flight byte limit is reached.
        """
        if self.in_flight_bytes >= MAX_IN_FLIGHT_BYTES:
            return None

        expected = self._expected_state()
        regions = compute_diff(expected, self._target)
        if not regions:
            return None

        builder = HostPacketBuilder(max_bytes=MAX_PACKET_BYTES)
        builder.write_sysex_header(device_index)
        builder.begin_data_changes(self._packet_index)

        encoder = DataChangeEncoder(builder.writer)
        encode_regions(encoder, regions, self._target)
        encoder.end(is_last=True)

        packet = builder.build()
        if now is None:
            now = time.monotonic()

        self._messages.append(
            _InFlightMessage(
                packet_index=self._packet_index,
                packet_data=packet,
                result_state=bytearray(self._target),
                payload_size=len(packet),
                last_send_time=now,
            )
        )
        self._packet_index = (self._packet_index + 1) & _COUNTER_MASK
        return packet

    def handle_ack(self, packet_index: int) -> bool:
        """Process an ACK, confirming all messages up to the given index.

        Updates confirmed device state to match the ACK'd message's
        result state. Returns True if the ACK matched an in-flight message.
        """
        found = False
        while self._messages:
            msg = self._messages[0]
            for i, b in enumerate(msg.result_state):
                self._device_state[i] = b
            self._messages.popleft()
            if msg.packet_index == packet_index:
                found = True
                break
        return found

    def get_retransmit(self, now: float | None = None) -> bytes | None:
        """Get a packet to retransmit if the oldest in-flight message timed out."""
        if not self._messages:
            return None
        if now is None:
            now = time.monotonic()
        oldest = self._messages[0]
        if now - oldest.last_send_time >= RETRANSMIT_TIMEOUT:
            oldest.last_send_time = now
            return oldest.packet_data
        return None

    def _expected_state(self) -> bytearray:
        """Get the optimistic expected device state.

        If messages are in-flight, returns the tail message's result state
        (what the device will have once all pending ACKs arrive). Otherwise,
        returns confirmed device state with unknown bytes as 0x00 — matching
        C++ uint16→uint8 truncation where 0x100 becomes 0x00.
        """
        if self._messages:
            return bytearray(self._messages[-1].result_state)
        return bytearray(b & 0xFF if b != _UNKNOWN else 0 for b in self._device_state)
