"""Tests for the blocksd API event broadcaster."""

from __future__ import annotations

import asyncio

import pytest

from blocksd.api.events import VALID_EVENTS, EventBroadcaster, _block_type_to_api, _device_to_dict
from blocksd.device.models import BlockType, ButtonEvent, DeviceInfo, TouchEvent


@pytest.fixture
def broadcaster() -> EventBroadcaster:
    return EventBroadcaster()


@pytest.fixture
def lightpad() -> DeviceInfo:
    return DeviceInfo(
        uid=12345,
        topology_index=0,
        serial="LPB1234567890AB",
        block_type=BlockType.LIGHTPAD,
        battery_level=85,
        battery_charging=False,
    )


class TestEventBroadcaster:
    """Event subscription and broadcasting."""

    def test_subscribe_returns_id(self, broadcaster: EventBroadcaster) -> None:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        sub_id = broadcaster.subscribe(queue, {"device", "touch"})
        assert isinstance(sub_id, int)
        assert broadcaster.subscriber_count == 1

    def test_subscribe_increments_id(self, broadcaster: EventBroadcaster) -> None:
        q1: asyncio.Queue[dict] = asyncio.Queue()
        q2: asyncio.Queue[dict] = asyncio.Queue()
        id1 = broadcaster.subscribe(q1, {"device"})
        id2 = broadcaster.subscribe(q2, {"device"})
        assert id2 > id1

    def test_unsubscribe(self, broadcaster: EventBroadcaster) -> None:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        sub_id = broadcaster.subscribe(queue, {"device"})
        assert broadcaster.subscriber_count == 1
        broadcaster.unsubscribe(sub_id)
        assert broadcaster.subscriber_count == 0

    def test_unsubscribe_nonexistent_is_noop(self, broadcaster: EventBroadcaster) -> None:
        broadcaster.unsubscribe(999)

    def test_device_added_broadcast(
        self, broadcaster: EventBroadcaster, lightpad: DeviceInfo
    ) -> None:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        broadcaster.subscribe(queue, {"device"})

        broadcaster.broadcast_device_added(lightpad)

        assert not queue.empty()
        msg = queue.get_nowait()
        assert msg["type"] == "device_added"
        assert msg["device"]["uid"] == 12345
        assert msg["device"]["serial"] == "LPB1234567890AB"

    def test_device_removed_broadcast(
        self, broadcaster: EventBroadcaster, lightpad: DeviceInfo
    ) -> None:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        broadcaster.subscribe(queue, {"device"})

        broadcaster.broadcast_device_removed(lightpad)

        msg = queue.get_nowait()
        assert msg["type"] == "device_removed"
        assert msg["uid"] == 12345

    def test_touch_broadcast(self, broadcaster: EventBroadcaster) -> None:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        broadcaster.subscribe(queue, {"touch"})

        event = TouchEvent(
            uid=42,
            timestamp=0,
            touch_index=0,
            x=0.5,
            y=0.75,
            z=0.8,
            is_start=True,
        )
        broadcaster.broadcast_touch(event)

        msg = queue.get_nowait()
        assert msg["type"] == "touch"
        assert msg["action"] == "start"
        assert msg["x"] == 0.5
        assert msg["y"] == 0.75
        assert msg["z"] == 0.8

    def test_touch_end_action(self, broadcaster: EventBroadcaster) -> None:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        broadcaster.subscribe(queue, {"touch"})

        event = TouchEvent(uid=42, timestamp=0, touch_index=0, x=0, y=0, z=0, is_end=True)
        broadcaster.broadcast_touch(event)

        msg = queue.get_nowait()
        assert msg["action"] == "end"

    def test_touch_move_action(self, broadcaster: EventBroadcaster) -> None:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        broadcaster.subscribe(queue, {"touch"})

        event = TouchEvent(uid=42, timestamp=0, touch_index=0, x=0, y=0, z=0)
        broadcaster.broadcast_touch(event)

        msg = queue.get_nowait()
        assert msg["action"] == "move"

    def test_button_broadcast(self, broadcaster: EventBroadcaster) -> None:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        broadcaster.subscribe(queue, {"button"})

        event = ButtonEvent(uid=42, timestamp=0, button_id=0, is_down=True)
        broadcaster.broadcast_button(event)

        msg = queue.get_nowait()
        assert msg["type"] == "button"
        assert msg["action"] == "press"

    def test_button_release(self, broadcaster: EventBroadcaster) -> None:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        broadcaster.subscribe(queue, {"button"})

        event = ButtonEvent(uid=42, timestamp=0, button_id=0, is_down=False)
        broadcaster.broadcast_button(event)

        msg = queue.get_nowait()
        assert msg["action"] == "release"

    def test_filtering_by_category(self, broadcaster: EventBroadcaster) -> None:
        """Subscribers only get events they subscribed to."""
        device_queue: asyncio.Queue[dict] = asyncio.Queue()
        touch_queue: asyncio.Queue[dict] = asyncio.Queue()
        broadcaster.subscribe(device_queue, {"device"})
        broadcaster.subscribe(touch_queue, {"touch"})

        # Broadcast device event — only device subscriber gets it
        dev = DeviceInfo(uid=1, topology_index=0, serial="LPB000", block_type=BlockType.LIGHTPAD)
        broadcaster.broadcast_device_added(dev)

        assert not device_queue.empty()
        assert touch_queue.empty()

    def test_invalid_event_types_ignored(self, broadcaster: EventBroadcaster) -> None:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        sub_id = broadcaster.subscribe(queue, {"device", "invalid", "nonsense"})
        # Only "device" is valid
        sub = broadcaster._subscribers[sub_id]
        assert sub.events == {"device"}

    def test_full_queue_drops_subscriber(self, broadcaster: EventBroadcaster) -> None:
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=1)
        broadcaster.subscribe(queue, {"device"})

        dev = DeviceInfo(uid=1, topology_index=0, serial="LPB000", block_type=BlockType.LIGHTPAD)

        # First message fills the queue
        broadcaster.broadcast_device_added(dev)
        assert broadcaster.subscriber_count == 1

        # Second message overflows — subscriber gets dropped
        broadcaster.broadcast_device_added(dev)
        assert broadcaster.subscriber_count == 0


class TestDeviceSerialization:
    """Device model to API dict conversion."""

    def test_device_to_dict(self) -> None:
        dev = DeviceInfo(
            uid=99999,
            topology_index=0,
            serial="LKB_SERIALNUMBER",
            block_type=BlockType.LUMI_KEYS,
            version="1.2.3",
            battery_level=50,
            battery_charging=True,
        )
        d = _device_to_dict(dev)
        assert d["uid"] == 99999
        assert d["block_type"] == "lumi_keys"
        assert d["grid_width"] == 0
        assert d["grid_height"] == 0
        assert d["battery_level"] == 50
        assert d["battery_charging"] is True
        assert d["firmware_version"] == "1.2.3"

    def test_block_type_mapping(self) -> None:
        assert _block_type_to_api(BlockType.LIGHTPAD) == "lightpad"
        assert _block_type_to_api(BlockType.LIGHTPAD_M) == "lightpad_m"
        assert _block_type_to_api(BlockType.LUMI_KEYS) == "lumi_keys"
        assert _block_type_to_api(BlockType.SEABOARD) == "seaboard"
        assert _block_type_to_api(BlockType.LIVE) == "live"
        assert _block_type_to_api(BlockType.LOOP) == "loop"
        assert _block_type_to_api(BlockType.TOUCH) == "touch"
        assert _block_type_to_api(BlockType.DEV_CTRL) == "developer"
        assert _block_type_to_api(BlockType.UNKNOWN) == "unknown"

    def test_valid_events_set(self) -> None:
        assert {"device", "touch", "button", "config", "topology"} == VALID_EVENTS
