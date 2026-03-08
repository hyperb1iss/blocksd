"""Host packet decoder — parse device→host SysEx messages.

Ported from roli_HostPacketDecoder.h.
"""

from __future__ import annotations

from typing import Protocol

from blocksd.protocol.checksum import calculate_checksum
from blocksd.protocol.constants import (
    ROLI_SYSEX_HEADER,
    BitSize,
    MessageFromDevice,
)
from blocksd.protocol.packing import Packed7BitReader


class PacketHandler(Protocol):
    """Interface for handling decoded device messages."""

    def on_topology_begin(self, num_devices: int, num_connections: int) -> None: ...
    def on_topology_device(
        self, serial: str, battery_level: int, battery_charging: bool
    ) -> None: ...
    def on_topology_connection(
        self, dev1_idx: int, port1: int, dev2_idx: int, port2: int
    ) -> None: ...
    def on_topology_end(self) -> None: ...
    def on_packet_ack(self, device_index: int, counter: int) -> None: ...
    def on_touch(
        self,
        device_index: int,
        timestamp: int,
        touch_index: int,
        x: int,
        y: int,
        z: int,
        vx: int,
        vy: int,
        vz: int,
        is_start: bool,
        is_end: bool,
    ) -> None: ...
    def on_button(
        self, device_index: int, timestamp: int, button_id: int, is_down: bool
    ) -> None: ...
    def on_config_update(
        self, device_index: int, item: int, value: int, min_val: int, max_val: int
    ) -> None: ...
    def on_log_message(self, device_index: int, message: str) -> None: ...


def decode_packet(sysex_data: bytes, handler: PacketHandler) -> bool:
    """Decode a device→host SysEx packet and dispatch to handler.

    Returns True if the packet was valid and processed.
    """
    header_len = len(ROLI_SYSEX_HEADER)

    # Validate header
    if len(sysex_data) < header_len + 3:  # header + index + checksum + F7
        return False
    if sysex_data[:header_len] != ROLI_SYSEX_HEADER:
        return False
    if sysex_data[-1] != 0xF7:
        return False

    device_index = sysex_data[header_len] & 0x3F
    payload = sysex_data[header_len + 1 : -2]  # between index byte and checksum
    received_checksum = sysex_data[-2]

    if calculate_checksum(payload) != received_checksum:
        return False

    reader = Packed7BitReader(payload)

    # First 32 bits: packet timestamp
    _timestamp = reader.read_bits(BitSize.PACKET_TIMESTAMP)

    # Process messages until we run out of bits
    while reader.remaining_bits >= BitSize.MESSAGE_TYPE:
        msg_type = reader.read_bits(BitSize.MESSAGE_TYPE)
        _decode_message(reader, msg_type, device_index, handler)

    return True


def _decode_message(
    reader: Packed7BitReader,
    msg_type: int,
    device_index: int,
    handler: PacketHandler,
) -> None:
    """Decode a single message within a packet."""
    # Topology messages, touch, buttons, config, etc. will be decoded here.
    # This is the main dispatch — implementations will be filled in during Phase 1.
    _ = reader, msg_type, device_index, handler
