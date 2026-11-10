"""System-setting sync requests reach hardware without changing its values."""

import asyncio
import json
from unittest.mock import Mock

import pytest

from blocksd.api.server import ApiServer, WebServer
from blocksd.protocol.builder import build_config_request_factory_sync
from blocksd.topology.detector import MidiPortPair
from blocksd.topology.device_group import DeviceGroup, GroupState
from blocksd.topology.manager import TopologyManager
from tests.topology.test_device_group import MockMidiConnection, _build_topology_packet

# SDK addRequestFactorySyncMessage: message 0x10, command 0x02, checksum 0x44.
FACTORY_SYNC = bytes.fromhex("f00021107700100244f7")


@pytest.fixture
def connected():
    connection = MockMidiConnection()
    group = DeviceGroup(connection)
    group.state = GroupState.REQUESTING_TOPOLOGY
    group._process_message(_build_topology_packet(["LKB0000000000000"]))
    device = group.topology.devices[0]
    group.on_packet_ack(device.topology_index, 0)
    manager = TopologyManager()
    manager._groups["keyboard"] = Mock(group=group)
    return manager, group, connection, device


def test_factory_sync_matches_sdk_wire_format():
    assert build_config_request_factory_sync(0) == FACTORY_SYNC
    assert build_config_request_factory_sync(22) == bytes.fromhex("f00021107716100244f7")


def test_api_connection_requests_factory_settings_once(connected):
    _manager, group, connection, device = connected
    assert connection.sent == [FACTORY_SYNC]
    group.on_packet_ack(device.topology_index, 1)
    assert connection.sent == [FACTORY_SYNC]
    assert group.get_config(device.uid) == {}


@pytest.mark.parametrize("server_class", [ApiServer, WebServer])
@pytest.mark.parametrize("target", ["serial", "uid"])
def test_refresh_routes_request_and_returns_only_observed_values(connected, server_class, target):
    manager, group, connection, device = connected
    group.on_config_update(device.topology_index, 4, -1, -4, 6)
    other_connection = MockMidiConnection()
    manager._groups = {"other": Mock(group=DeviceGroup(other_connection)), **manager._groups}
    server = server_class(manager)
    request = {"type": "config_get", target: getattr(device, target), "refresh": True, "id": "read"}
    response, _ = server._handle_json(json.dumps(request).encode(), asyncio.Queue(), None)
    assert response is not None
    assert response["type"] == "config_values"
    assert response["id"] == "read"
    assert response["values"] == [{"item": 4, "value": -1, "min": -4, "max": 6, "writable": True}]
    assert connection.sent == [FACTORY_SYNC, FACTORY_SYNC]
    assert other_connection.sent == []
    assert group.get_config(device.uid)[4].value == -1


@pytest.mark.parametrize("refresh", [None, False])
def test_cached_get_does_not_send_a_hardware_request(connected, refresh):
    manager, _group, connection, device = connected
    request = {"type": "config_get", "uid": device.uid}
    if refresh is not None:
        request["refresh"] = refresh
    response, _ = ApiServer(manager)._handle_json(
        json.dumps(request).encode(), asyncio.Queue(), None
    )
    assert response is not None
    assert response["values"] == []
    assert connection.sent == [FACTORY_SYNC]


@pytest.mark.parametrize("refresh", [None, 0, 1, "true", []])
def test_refresh_requires_boolean(connected, refresh):
    manager, _group, connection, device = connected
    response, _ = ApiServer(manager)._handle_json(
        json.dumps({"type": "config_get", "uid": device.uid, "refresh": refresh}).encode(),
        asyncio.Queue(),
        None,
    )
    assert response is not None
    assert response["type"] == "error"
    assert response["message"] == "refresh must be a boolean"
    assert connection.sent == [FACTORY_SYNC]


@pytest.mark.parametrize("failure", ["disconnected", "not_ready", "send_failed"])
def test_refresh_reports_device_or_send_failure(connected, failure):
    manager, group, connection, device = connected
    if failure == "disconnected":
        group._remove_device(device.uid)
    elif failure == "not_ready":
        group._pings.clear()
    else:
        connection.close()
    response, _ = ApiServer(manager)._handle_json(
        json.dumps(
            {"type": "config_get", "uid": device.uid, "refresh": True, "id": "read"}
        ).encode(),
        asyncio.Queue(),
        None,
    )
    assert response is not None
    assert response["type"] == "error"
    assert response["id"] == "read"
    assert (
        "not connected" in response["message"]
        or "not ready or MIDI send failed" in response["message"]
    )
    assert connection.sent == [FACTORY_SYNC]


def test_device_strings_stop_at_nul_and_blank_names_keep_existing_name(connected):
    _manager, group, _connection, device = connected
    group.on_device_name(device.topology_index, "studio keys\x00trailing")
    group.on_device_version(device.topology_index, "1.3.9\x00trailing")
    assert device.name == "studio keys"
    assert device.version == "1.3.9"
    group.on_device_name(device.topology_index, "\x00")
    group.on_device_name(device.topology_index, "   ")
    assert device.name == "studio keys"


@pytest.mark.parametrize("name", ["\x02bP\x07\x00", "\x00"])
def test_invalid_hardware_names_preserve_model_fallback(connected, name):
    _manager, group, _connection, device = connected
    assert device.name == ""
    group.on_device_name(device.topology_index, name)
    assert device.name == ""


@pytest.mark.parametrize("server_class", [ApiServer, WebServer])
async def test_config_reset_invalidates_cache_and_precedes_fresh_events(monkeypatch, server_class):
    from blocksd.topology import manager as module

    async def run_group(_self):
        await asyncio.Event().wait()

    monkeypatch.setattr(module, "open_connection", lambda *_args, **_kwargs: MockMidiConnection())
    monkeypatch.setattr(DeviceGroup, "run", run_group)
    manager = TopologyManager()
    server = server_class(manager)
    server._attach_events()
    queue = asyncio.Queue()
    server._broadcaster.subscribe(queue, {"config"})
    unrelated = asyncio.Queue()
    server._broadcaster.subscribe(unrelated, {"device"})
    try:
        manager._add_group(MidiPortPair(0, 0, "keyboard"))
        group = manager.groups[0]
        group.state = GroupState.REQUESTING_TOPOLOGY
        group._process_message(_build_topology_packet(["LKB0000000000000"]))
        device = group.topology.devices[0]
        group.on_packet_ack(device.topology_index, 0)
        while not unrelated.empty():
            unrelated.get_nowait()

        group.on_config_update(device.topology_index, 4, -1, -4, 6)
        assert queue.get_nowait()["type"] == "config_changed"
        group.on_config_factory_sync_reset(device.topology_index)
        assert manager.get_config(device.uid) == {}
        group.on_config_update(device.topology_index, 5, 2, -11, 11)
        assert queue.get_nowait() == {
            "type": "config_reset",
            "uid": device.uid,
            "serial": device.serial,
        }
        fresh = queue.get_nowait()
        assert fresh["type"] == "config_changed"
        assert fresh["item"] == 5
        assert set(manager.get_config(device.uid)) == {5}
        assert unrelated.empty()

        group.on_config_factory_sync_reset(device.topology_index)
        group.on_config_factory_sync_end(device.topology_index)
        assert queue.get_nowait()["type"] == "config_reset"
        assert queue.empty()
        assert manager.get_config(device.uid) == {}
        await server.stop()
        assert manager.on_config_reset == []
        group.on_config_factory_sync_reset(device.topology_index)
        assert queue.empty()
    finally:
        await server.stop()
        await manager._shutdown()
