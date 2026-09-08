"""Physical key frames stay separate from Lightpad bitmap frames."""

import asyncio
import base64
import json
from unittest.mock import Mock

import pytest

from blocksd.api.server import ApiServer, WebServer
from blocksd.device.models import BlockType, DeviceInfo


@pytest.fixture(params=[ApiServer, WebServer])
def key_api(request):
    manager = Mock()
    manager.find_device.return_value = DeviceInfo(
        uid=7, topology_index=1, serial="LKB000", block_type=BlockType.LUMI_KEYS
    )
    manager.set_key_led_data.return_value = True
    return request.param(manager), manager


def send(server, message):
    response, subscription = server._handle_json(
        json.dumps(message).encode(), asyncio.Queue(), None
    )
    assert subscription is None
    return response


def test_key_frame_preserves_physical_order_and_request_id(key_api):
    server, manager = key_api
    pixels = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255]) * 8
    response = send(
        server,
        {"type": "key_frame", "uid": 7, "pixels": base64.b64encode(pixels).decode(), "id": 0},
    )
    assert response == {"type": "key_frame_ack", "uid": 7, "accepted": True, "id": 0}
    manager.set_key_led_data.assert_called_once_with(7, bytes.fromhex("1f00e00700f8") * 8)
    manager.set_led_data.assert_not_called()


def test_key_frame_applies_existing_brightness(key_api):
    server, manager = key_api
    send(server, {"type": "brightness", "uid": 7, "value": 127.9})
    response = send(
        server,
        {"type": "key_frame", "uid": 7, "pixels": base64.b64encode(b"\xff" * 72).decode()},
    )
    assert response["accepted"] is True
    manager.set_key_led_data.assert_called_once_with(7, bytes.fromhex("ef7b") * 24)


@pytest.mark.parametrize("uid", [None, True, "7", [], {}])
def test_key_frame_rejects_invalid_uid_without_writes(key_api, uid):
    server, manager = key_api
    response = send(
        server, {"type": "key_frame", "uid": uid, "pixels": base64.b64encode(bytes(72)).decode()}
    )
    assert response["type"] == "key_frame_ack"
    assert response["accepted"] is False
    manager.find_device.assert_not_called()
    manager.set_key_led_data.assert_not_called()
    manager.set_led_data.assert_not_called()


@pytest.mark.parametrize("size", [0, 48, 71, 73, 675])
def test_key_frame_rejects_wrong_frame_size_without_writes(key_api, size):
    server, manager = key_api
    response = send(
        server, {"type": "key_frame", "uid": 7, "pixels": base64.b64encode(bytes(size)).decode()}
    )
    assert response["accepted"] is False
    manager.set_key_led_data.assert_not_called()
    manager.set_led_data.assert_not_called()


@pytest.mark.parametrize("pixels", [None, [], {}, "!invalid-base64!"])
def test_key_frame_rejects_invalid_encoding_without_writes(key_api, pixels):
    server, manager = key_api
    response = send(server, {"type": "key_frame", "uid": 7, "pixels": pixels})
    assert response["accepted"] is False
    manager.set_key_led_data.assert_not_called()
    manager.set_led_data.assert_not_called()


@pytest.mark.parametrize("block_type", [None, *[t for t in BlockType if t != BlockType.LUMI_KEYS]])
def test_key_frame_rejects_missing_or_unsupported_device(key_api, block_type):
    server, manager = key_api
    manager.find_device.return_value = (
        None
        if block_type is None
        else DeviceInfo(uid=7, topology_index=1, serial="OTHER", block_type=block_type)
    )
    response = send(
        server, {"type": "key_frame", "uid": 7, "pixels": base64.b64encode(bytes(72)).decode()}
    )
    assert response["accepted"] is False
    manager.set_key_led_data.assert_not_called()
    manager.set_led_data.assert_not_called()


def test_key_frame_reports_manager_rejection(key_api):
    server, manager = key_api
    manager.set_key_led_data.return_value = False
    response = send(
        server, {"type": "key_frame", "uid": 7, "pixels": base64.b64encode(bytes(72)).decode()}
    )
    assert response == {"type": "key_frame_ack", "uid": 7, "accepted": False}


def test_discovery_exposes_key_count_without_bitmap_dimensions(key_api):
    server, manager = key_api
    manager.devices = [manager.find_device.return_value]
    device = send(server, {"type": "discover"})["devices"][0]
    assert device["key_count"] == 24
    assert device["grid_width"] == device["grid_height"] == 0
