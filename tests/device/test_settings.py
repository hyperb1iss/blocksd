"""Settings preserve protocol identity, signed values, and device readback."""

from unittest.mock import Mock

import pytest

from blocksd.device.config_ids import BlockConfigId
from blocksd.device.models import ConfigValue
from blocksd.device.settings import setting_schema, validate_setting
from blocksd.protocol.builder import build_config_request, build_config_set
from blocksd.protocol.constants import BitSize, ConfigCommand, MessageFromDevice
from blocksd.protocol.decoder import decode_packet
from blocksd.topology.device_group import DeviceGroup
from tests.protocol.test_decoder import RecordingHandler, _build_device_packet, _make_writer
from tests.topology.test_device_group import MockMidiConnection, _build_topology_packet


def test_metadata_uses_system_ids_and_does_not_mislabel_tracking():
    schema = {
        item["key"]: item for item in setting_schema([value.value for value in BlockConfigId])
    }
    assert schema["midi_start_channel"]["item"] == 0
    assert schema["midi_end_channel"]["item"] == 1
    assert schema["mpe_zone"]["item"] == 40
    assert schema["x_tracking_mode"]["item"] == 30
    assert schema["glide_sensitivity"]["item"] == 11
    assert schema["slide_sensitivity"]["item"] == 12
    assert schema["fixed_velocity"]["kind"] == "toggle"


@pytest.mark.parametrize("command", [ConfigCommand.UPDATE_CONFIG, ConfigCommand.SET_CONFIG])
@pytest.mark.parametrize("value", [-(2**31), -11, -1, 0, 2**31 - 1])
def test_config_decoder_matches_sdk_signed_int32(command, value):
    writer = _make_writer()
    writer.write_bits(MessageFromDevice.CONFIG_MESSAGE, BitSize.MESSAGE_TYPE)
    writer.write_bits(command, BitSize.CONFIG_COMMAND)
    writer.write_bits(5, BitSize.CONFIG_ITEM_INDEX)
    writer.write_bits(value, BitSize.CONFIG_ITEM_VALUE)
    if command == ConfigCommand.UPDATE_CONFIG:
        writer.write_bits(-(2**31), BitSize.CONFIG_ITEM_VALUE)
        writer.write_bits(2**31 - 1, BitSize.CONFIG_ITEM_VALUE)
    handler = RecordingHandler()
    decode_packet(_build_device_packet(0, writer), handler)
    expected = (0, 5, value)
    if command == ConfigCommand.UPDATE_CONFIG:
        expected += (-(2**31), 2**31 - 1)
    assert handler.calls[0][1] == expected


def test_config_sends_write_before_readback_and_preserves_observed_bounds(monkeypatch):
    connection = MockMidiConnection()
    group = DeviceGroup(connection)
    group._process_message(_build_topology_packet(["LKB0123456789ABC"]))
    device = next(iter(group._devices.values()))
    group._update_api_ping(device.uid)
    group.on_config_update(0, 5, -2, -11, 11)
    connection.sent.clear()
    assert group.set_config(device.uid, 5, 3)
    assert connection.sent == [build_config_set(0, 5, 3), build_config_request(0, 5)]
    assert group.get_config(device.uid)[5].value == -2
    group.on_config_set(0, 5, 3)
    assert group.get_config(device.uid)[5] == ConfigValue(5, 3, -11, 11, has_range=True)
    sender = Mock(return_value=False)
    monkeypatch.setattr(connection, "send", sender)
    assert not group.set_config(device.uid, 5, 4)
    sender.assert_called_once_with(build_config_set(0, 5, 4))
    sender.reset_mock()
    sender.side_effect = [True, False]
    assert not group.set_config(device.uid, 5, 4)
    assert sender.call_count == 2
    assert group.get_config(device.uid)[5].value == 3
    sender.side_effect = None
    sender.reset_mock()
    assert not group.set_config(device.uid, 5, 100)
    assert not group.set_config(device.uid, 99, 1)
    sender.assert_not_called()


@pytest.mark.parametrize("value", [True, 1.5, 2**31, -(2**31) - 1])
def test_setting_validation_rejects_non_int32(value):
    with pytest.raises(ValueError):
        validate_setting({5: ConfigValue(5, 0, -(2**31), 2**31 - 1, has_range=True)}, 5, value)
