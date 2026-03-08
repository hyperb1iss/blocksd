"""Host packet decoder — parse device→host SysEx messages.

Ported from roli_HostPacketDecoder.h.
"""

from __future__ import annotations

from typing import Protocol

from blocksd.protocol.checksum import calculate_checksum
from blocksd.protocol.constants import (
    MAX_BLOCKS_IN_TOPOLOGY_PACKET,
    MAX_CONNECTIONS_IN_TOPOLOGY_PACKET,
    PROTOCOL_VERSION,
    ROLI_SYSEX_HEADER,
    BitSize,
    ConfigCommand,
    MessageFromDevice,
)
from blocksd.protocol.packing import Packed7BitReader

# Bit counts for bounds-checking before reading
_TOPOLOGY_DEVICE_BITS = BitSize.SERIAL_CHAR * BitSize.SERIAL_LENGTH + (
    BitSize.TOPOLOGY_INDEX + BitSize.BATTERY_LEVEL + BitSize.BATTERY_CHARGING
)
_TOPOLOGY_CONNECTION_BITS = (
    BitSize.TOPOLOGY_INDEX
    + BitSize.CONNECTOR_PORT
    + BitSize.TOPOLOGY_INDEX
    + BitSize.CONNECTOR_PORT
)
_TOUCH_BODY_BITS = (
    BitSize.TIMESTAMP_OFFSET
    + BitSize.TOUCH_INDEX
    + BitSize.TOUCH_X
    + BitSize.TOUCH_Y
    + BitSize.TOUCH_Z
)
_TOUCH_VELOCITY_BODY_BITS = (
    _TOUCH_BODY_BITS + BitSize.TOUCH_VX + BitSize.TOUCH_VY + BitSize.TOUCH_VZ
)
_BUTTON_BODY_BITS = BitSize.TIMESTAMP_OFFSET + BitSize.CONTROL_BUTTON_ID


class PacketHandler(Protocol):
    """Interface for handling decoded device messages."""

    def on_topology_begin(self, num_devices: int, num_connections: int) -> None: ...
    def on_topology_extend(self, num_devices: int, num_connections: int) -> None: ...
    def on_topology_device(
        self, topology_index: int, serial: str, battery_level: int, battery_charging: bool
    ) -> None: ...
    def on_topology_connection(
        self, dev1_idx: int, port1: int, dev2_idx: int, port2: int
    ) -> None: ...
    def on_topology_end(self) -> None: ...
    def on_device_version(self, topology_index: int, version: str) -> None: ...
    def on_device_name(self, topology_index: int, name: str) -> None: ...
    def on_packet_ack(self, device_index: int, counter: int) -> None: ...
    def on_firmware_update_ack(self, device_index: int, code: int, detail: int) -> None: ...
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
    def on_program_event(
        self, device_index: int, timestamp: int, data: tuple[int, int, int]
    ) -> None: ...
    def on_config_update(
        self, device_index: int, item: int, value: int, min_val: int, max_val: int
    ) -> None: ...
    def on_config_set(self, device_index: int, item: int, value: int) -> None: ...
    def on_config_factory_sync_end(self, device_index: int) -> None: ...
    def on_config_factory_sync_reset(self, device_index: int) -> None: ...
    def on_log_message(self, device_index: int, message: str) -> None: ...


def decode_packet(sysex_data: bytes, handler: PacketHandler) -> bool:
    """Decode a device→host SysEx packet and dispatch to handler.

    Returns True if the packet was valid and processed.
    """
    header_len = len(ROLI_SYSEX_HEADER)

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

    if reader.remaining_bits < BitSize.PACKET_TIMESTAMP:
        return False

    packet_timestamp = reader.read_bits(BitSize.PACKET_TIMESTAMP)

    while reader.remaining_bits >= BitSize.MESSAGE_TYPE:
        msg_type = reader.read_bits(BitSize.MESSAGE_TYPE)
        if msg_type == 0:
            break
        if not _decode_message(reader, msg_type, device_index, packet_timestamp, handler):
            break

    return True


# ── Message dispatch ──────────────────────────────────────────────────────────


def _decode_message(
    reader: Packed7BitReader,
    msg_type: int,
    device_index: int,
    packet_timestamp: int,
    handler: PacketHandler,
) -> bool:
    """Decode a single message within a packet."""
    match msg_type:
        case MessageFromDevice.DEVICE_TOPOLOGY:
            return _handle_topology(reader, handler, new_topology=True)
        case MessageFromDevice.DEVICE_TOPOLOGY_EXTEND:
            return _handle_topology(reader, handler, new_topology=False)
        case MessageFromDevice.DEVICE_TOPOLOGY_END:
            return _handle_topology_end(reader, handler)
        case MessageFromDevice.DEVICE_VERSION:
            return _handle_version(reader, handler)
        case MessageFromDevice.DEVICE_NAME:
            return _handle_name(reader, handler)
        case MessageFromDevice.TOUCH_START:
            return _handle_touch(reader, device_index, packet_timestamp, handler, True, False)
        case MessageFromDevice.TOUCH_MOVE:
            return _handle_touch(reader, device_index, packet_timestamp, handler, False, False)
        case MessageFromDevice.TOUCH_END:
            return _handle_touch(reader, device_index, packet_timestamp, handler, False, True)
        case MessageFromDevice.TOUCH_START_WITH_VELOCITY:
            return _handle_touch_velocity(
                reader, device_index, packet_timestamp, handler, True, False
            )
        case MessageFromDevice.TOUCH_MOVE_WITH_VELOCITY:
            return _handle_touch_velocity(
                reader, device_index, packet_timestamp, handler, False, False
            )
        case MessageFromDevice.TOUCH_END_WITH_VELOCITY:
            return _handle_touch_velocity(
                reader, device_index, packet_timestamp, handler, False, True
            )
        case MessageFromDevice.CONTROL_BUTTON_DOWN:
            return _handle_button(reader, device_index, packet_timestamp, handler, True)
        case MessageFromDevice.CONTROL_BUTTON_UP:
            return _handle_button(reader, device_index, packet_timestamp, handler, False)
        case MessageFromDevice.PROGRAM_EVENT_MESSAGE:
            return _handle_program_event(reader, device_index, packet_timestamp, handler)
        case MessageFromDevice.PACKET_ACK:
            return _handle_packet_ack(reader, device_index, handler)
        case MessageFromDevice.FIRMWARE_UPDATE_ACK:
            return _handle_firmware_update_ack(reader, device_index, handler)
        case MessageFromDevice.CONFIG_MESSAGE:
            return _handle_config(reader, device_index, handler)
        case MessageFromDevice.LOG_MESSAGE:
            return _handle_log(reader, device_index, handler)
        case _:
            return False


# ── Topology ──────────────────────────────────────────────────────────────────


def _handle_topology(
    reader: Packed7BitReader, handler: PacketHandler, *, new_topology: bool
) -> bool:
    needed = BitSize.PROTOCOL_VERSION + BitSize.DEVICE_COUNT + BitSize.CONNECTION_COUNT
    if reader.remaining_bits < needed:
        return False

    protocol_version = reader.read_bits(BitSize.PROTOCOL_VERSION)
    if protocol_version > PROTOCOL_VERSION:
        return False

    num_devices = reader.read_bits(BitSize.DEVICE_COUNT)
    num_connections = reader.read_bits(BitSize.CONNECTION_COUNT)

    body_bits = num_devices * _TOPOLOGY_DEVICE_BITS + num_connections * _TOPOLOGY_CONNECTION_BITS
    if reader.remaining_bits < body_bits:
        return False

    if new_topology:
        handler.on_topology_begin(num_devices, num_connections)
    else:
        handler.on_topology_extend(num_devices, num_connections)

    for _ in range(num_devices):
        _read_topology_device(reader, handler)

    for _ in range(num_connections):
        _read_topology_connection(reader, handler)

    # Auto-close if this isn't a full packet (no more chunks coming)
    if num_devices < MAX_BLOCKS_IN_TOPOLOGY_PACKET and (
        num_connections < MAX_CONNECTIONS_IN_TOPOLOGY_PACKET
    ):
        handler.on_topology_end()

    return True


def _read_topology_device(reader: Packed7BitReader, handler: PacketHandler) -> None:
    chars = [chr(reader.read_bits(BitSize.SERIAL_CHAR)) for _ in range(BitSize.SERIAL_LENGTH)]
    serial = "".join(c for c in chars if c != "\x00")
    topology_index = reader.read_bits(BitSize.TOPOLOGY_INDEX)
    battery_level = reader.read_bits(BitSize.BATTERY_LEVEL)
    battery_charging = bool(reader.read_bits(BitSize.BATTERY_CHARGING))
    handler.on_topology_device(topology_index, serial, battery_level, battery_charging)


def _read_topology_connection(reader: Packed7BitReader, handler: PacketHandler) -> None:
    dev1 = reader.read_bits(BitSize.TOPOLOGY_INDEX)
    port1 = reader.read_bits(BitSize.CONNECTOR_PORT)
    dev2 = reader.read_bits(BitSize.TOPOLOGY_INDEX)
    port2 = reader.read_bits(BitSize.CONNECTOR_PORT)
    handler.on_topology_connection(dev1, port1, dev2, port2)


def _handle_topology_end(reader: Packed7BitReader, handler: PacketHandler) -> bool:
    if reader.remaining_bits < BitSize.PROTOCOL_VERSION:
        return False
    protocol_version = reader.read_bits(BitSize.PROTOCOL_VERSION)
    if protocol_version > PROTOCOL_VERSION:
        return False
    handler.on_topology_end()
    return True


# ── Version / Name ────────────────────────────────────────────────────────────


def _handle_version(reader: Packed7BitReader, handler: PacketHandler) -> bool:
    if reader.remaining_bits < BitSize.TOPOLOGY_INDEX + 7:
        return False
    index = reader.read_bits(BitSize.TOPOLOGY_INDEX)
    length = reader.read_bits(7)
    if reader.remaining_bits < length * 7:
        return False
    version = "".join(chr(reader.read_bits(7)) for _ in range(length))
    handler.on_device_version(index, version)
    return True


def _handle_name(reader: Packed7BitReader, handler: PacketHandler) -> bool:
    if reader.remaining_bits < BitSize.TOPOLOGY_INDEX + 7:
        return False
    index = reader.read_bits(BitSize.TOPOLOGY_INDEX)
    length = reader.read_bits(7)
    if reader.remaining_bits < length * 7:
        return False
    name = "".join(chr(reader.read_bits(7)) for _ in range(length))
    handler.on_device_name(index, name)
    return True


# ── Touch ─────────────────────────────────────────────────────────────────────


def _handle_touch(
    reader: Packed7BitReader,
    device_index: int,
    packet_timestamp: int,
    handler: PacketHandler,
    is_start: bool,
    is_end: bool,
) -> bool:
    if reader.remaining_bits < _TOUCH_BODY_BITS:
        return False
    time_offset = reader.read_bits(BitSize.TIMESTAMP_OFFSET)
    touch_index = reader.read_bits(BitSize.TOUCH_INDEX)
    x = reader.read_bits(BitSize.TOUCH_X)
    y = reader.read_bits(BitSize.TOUCH_Y)
    z = reader.read_bits(BitSize.TOUCH_Z)
    ts = packet_timestamp + time_offset
    handler.on_touch(device_index, ts, touch_index, x, y, z, 0, 0, 0, is_start, is_end)
    return True


def _handle_touch_velocity(
    reader: Packed7BitReader,
    device_index: int,
    packet_timestamp: int,
    handler: PacketHandler,
    is_start: bool,
    is_end: bool,
) -> bool:
    if reader.remaining_bits < _TOUCH_VELOCITY_BODY_BITS:
        return False
    time_offset = reader.read_bits(BitSize.TIMESTAMP_OFFSET)
    touch_index = reader.read_bits(BitSize.TOUCH_INDEX)
    x = reader.read_bits(BitSize.TOUCH_X)
    y = reader.read_bits(BitSize.TOUCH_Y)
    z = reader.read_bits(BitSize.TOUCH_Z)
    vx = reader.read_bits(BitSize.TOUCH_VX)
    vy = reader.read_bits(BitSize.TOUCH_VY)
    vz = reader.read_bits(BitSize.TOUCH_VZ)
    ts = packet_timestamp + time_offset
    handler.on_touch(device_index, ts, touch_index, x, y, z, vx, vy, vz, is_start, is_end)
    return True


# ── Buttons ───────────────────────────────────────────────────────────────────


def _handle_button(
    reader: Packed7BitReader,
    device_index: int,
    packet_timestamp: int,
    handler: PacketHandler,
    is_down: bool,
) -> bool:
    if reader.remaining_bits < _BUTTON_BODY_BITS:
        return False
    time_offset = reader.read_bits(BitSize.TIMESTAMP_OFFSET)
    button_id = reader.read_bits(BitSize.CONTROL_BUTTON_ID)
    handler.on_button(device_index, packet_timestamp + time_offset, button_id, is_down)
    return True


# ── Program Events ────────────────────────────────────────────────────────────


def _handle_program_event(
    reader: Packed7BitReader,
    device_index: int,
    packet_timestamp: int,
    handler: PacketHandler,
) -> bool:
    if reader.remaining_bits < 3 * 32:
        return False
    d0 = reader.read_bits(32)
    d1 = reader.read_bits(32)
    d2 = reader.read_bits(32)
    handler.on_program_event(device_index, packet_timestamp, (d0, d1, d2))
    return True


# ── ACKs ──────────────────────────────────────────────────────────────────────


def _handle_packet_ack(reader: Packed7BitReader, device_index: int, handler: PacketHandler) -> bool:
    if reader.remaining_bits < BitSize.PACKET_COUNTER:
        return False
    counter = reader.read_bits(BitSize.PACKET_COUNTER)
    handler.on_packet_ack(device_index, counter)
    return True


def _handle_firmware_update_ack(
    reader: Packed7BitReader, device_index: int, handler: PacketHandler
) -> bool:
    if reader.remaining_bits < BitSize.FIRMWARE_UPDATE_ACK_CODE:
        return False
    code = reader.read_bits(BitSize.FIRMWARE_UPDATE_ACK_CODE)
    detail = reader.read_bits(BitSize.FIRMWARE_UPDATE_ACK_DETAIL)
    handler.on_firmware_update_ack(device_index, code, detail)
    return True


# ── Config ────────────────────────────────────────────────────────────────────


def _handle_config(reader: Packed7BitReader, device_index: int, handler: PacketHandler) -> bool:
    if reader.remaining_bits < BitSize.CONFIG_COMMAND:
        return False
    cmd = reader.read_bits(BitSize.CONFIG_COMMAND)

    if cmd == ConfigCommand.UPDATE_CONFIG:
        if reader.remaining_bits < 8 + 32 + 32 + 32:
            return False
        item = reader.read_bits(BitSize.CONFIG_ITEM_INDEX)
        value = reader.read_bits(BitSize.CONFIG_ITEM_VALUE)
        min_val = reader.read_bits(BitSize.CONFIG_ITEM_VALUE)
        max_val = reader.read_bits(BitSize.CONFIG_ITEM_VALUE)
        handler.on_config_update(device_index, item, value, min_val, max_val)

    elif cmd == ConfigCommand.SET_CONFIG:
        if reader.remaining_bits < 8 + 32:
            return False
        item = reader.read_bits(BitSize.CONFIG_ITEM_INDEX)
        value = reader.read_bits(BitSize.CONFIG_ITEM_VALUE)
        handler.on_config_set(device_index, item, value)

    elif cmd == ConfigCommand.FACTORY_SYNC_END:
        handler.on_config_factory_sync_end(device_index)

    elif cmd == ConfigCommand.FACTORY_SYNC_RESET:
        handler.on_config_factory_sync_reset(device_index)

    return True


# ── Log ───────────────────────────────────────────────────────────────────────


def _handle_log(reader: Packed7BitReader, device_index: int, handler: PacketHandler) -> bool:
    chars: list[str] = []
    while reader.remaining_bits >= 7:
        chars.append(chr(reader.read_bits(7)))
    handler.on_log_message(device_index, "".join(chars))
    return True
