"""Host packet builder — construct host→device SysEx messages.

Ported from roli_HostPacketBuilder.h.
"""

from __future__ import annotations

from blocksd.protocol.checksum import calculate_checksum
from blocksd.protocol.constants import (
    ROLI_SYSEX_HEADER,
    BitSize,
    DeviceCommand,
    MessageFromHost,
)
from blocksd.protocol.packing import Packed7BitWriter


class HostPacketBuilder:
    """Constructs ROLI BLOCKS SysEx packets for sending to devices."""

    def __init__(self, max_bytes: int = 64) -> None:
        self._header: bytes = b""
        self._writer = Packed7BitWriter(max_bytes)

    @property
    def writer(self) -> Packed7BitWriter:
        """Access the underlying bit writer (for DataChangeEncoder)."""
        return self._writer

    def write_sysex_header(self, device_index: int) -> None:
        """Write SysEx header with device topology index."""
        self._header = ROLI_SYSEX_HEADER + bytes([device_index & 0x3F])

    def device_command(self, command: DeviceCommand) -> None:
        """Write a device command message (beginAPIMode, ping, etc.)."""
        self._writer.write_bits(MessageFromHost.DEVICE_COMMAND, BitSize.MESSAGE_TYPE)
        self._writer.write_bits(command, BitSize.DEVICE_COMMAND)

    def begin_data_changes(self, packet_index: int) -> None:
        """Write SharedDataChange message header with 16-bit packet index."""
        self._writer.write_bits(MessageFromHost.SHARED_DATA_CHANGE, BitSize.MESSAGE_TYPE)
        self._writer.write_bits(packet_index, BitSize.PACKET_INDEX)

    def config_set(self, item: int, value: int) -> None:
        """Write a config set message."""
        from blocksd.protocol.constants import ConfigCommand

        self._writer.write_bits(MessageFromHost.CONFIG_MESSAGE, BitSize.MESSAGE_TYPE)
        self._writer.write_bits(ConfigCommand.SET_CONFIG, BitSize.CONFIG_COMMAND)
        self._writer.write_bits(item, BitSize.CONFIG_ITEM_INDEX)
        self._writer.write_bits(value & 0xFFFFFFFF, BitSize.CONFIG_ITEM_VALUE)

    def config_request(self, item: int) -> None:
        """Write a config request message."""
        from blocksd.protocol.constants import ConfigCommand

        self._writer.write_bits(MessageFromHost.CONFIG_MESSAGE, BitSize.MESSAGE_TYPE)
        self._writer.write_bits(ConfigCommand.REQUEST_CONFIG, BitSize.CONFIG_COMMAND)
        self._writer.write_bits(item, BitSize.CONFIG_ITEM_INDEX)

    def config_request_user_sync(self) -> None:
        """Request a full user config sync from the device."""
        from blocksd.protocol.constants import ConfigCommand

        self._writer.write_bits(MessageFromHost.CONFIG_MESSAGE, BitSize.MESSAGE_TYPE)
        self._writer.write_bits(ConfigCommand.REQUEST_USER_SYNC, BitSize.CONFIG_COMMAND)

    def build(self) -> bytes:
        """Finalize and return the complete SysEx message."""
        payload = self._writer.get_data()
        checksum = calculate_checksum(payload)
        return self._header + payload + bytes([checksum, 0xF7])


def build_device_command(device_index: int, command: DeviceCommand) -> bytes:
    """Convenience: build a single device command packet."""
    builder = HostPacketBuilder()
    builder.write_sysex_header(device_index)
    builder.device_command(command)
    return builder.build()


def build_ping(device_index: int = 0) -> bytes:
    """Build a ping packet."""
    return build_device_command(device_index, DeviceCommand.PING)


def build_begin_api_mode(device_index: int = 0) -> bytes:
    """Build a beginAPIMode packet."""
    return build_device_command(device_index, DeviceCommand.BEGIN_API_MODE)


def build_end_api_mode(device_index: int = 0) -> bytes:
    """Build an endAPIMode packet."""
    return build_device_command(device_index, DeviceCommand.END_API_MODE)


def build_request_topology(device_index: int = 0) -> bytes:
    """Build a requestTopologyMessage packet."""
    return build_device_command(device_index, DeviceCommand.REQUEST_TOPOLOGY)


def build_config_set(device_index: int, item: int, value: int) -> bytes:
    """Build a config set packet."""
    builder = HostPacketBuilder()
    builder.write_sysex_header(device_index)
    builder.config_set(item, value)
    return builder.build()


def build_config_request(device_index: int, item: int) -> bytes:
    """Build a config request packet."""
    builder = HostPacketBuilder()
    builder.write_sysex_header(device_index)
    builder.config_request(item)
    return builder.build()


def build_config_request_user_sync(device_index: int) -> bytes:
    """Build a user config sync request packet."""
    builder = HostPacketBuilder()
    builder.write_sysex_header(device_index)
    builder.config_request_user_sync()
    return builder.build()
