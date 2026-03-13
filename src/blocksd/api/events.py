"""Event subscription manager — broadcasts device/touch/button events to clients."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from blocksd.device.models import ButtonEvent, DeviceInfo, TouchEvent

log = logging.getLogger(__name__)

# Supported event categories
VALID_EVENTS = frozenset({"device", "touch", "button"})


class EventBroadcaster:
    """Manages client subscriptions and broadcasts events."""

    def __init__(self) -> None:
        self._subscribers: dict[int, _Subscriber] = {}
        self._next_id = 0

    def subscribe(self, queue: asyncio.Queue[dict[str, Any]], events: set[str]) -> int:
        """Register a client for event types. Returns subscription ID."""
        valid = events & VALID_EVENTS
        sub_id = self._next_id
        self._next_id += 1
        self._subscribers[sub_id] = _Subscriber(queue=queue, events=valid)
        log.debug("Client %d subscribed to %s", sub_id, valid)
        return sub_id

    def unsubscribe(self, sub_id: int) -> None:
        """Remove a client subscription."""
        self._subscribers.pop(sub_id, None)

    def broadcast_device_added(self, dev: DeviceInfo) -> None:
        """Broadcast a device_added event."""
        msg = {
            "type": "device_added",
            "device": _device_to_dict(dev),
        }
        self._broadcast("device", msg)

    def broadcast_device_removed(self, dev: DeviceInfo) -> None:
        """Broadcast a device_removed event."""
        msg = {
            "type": "device_removed",
            "uid": dev.uid,
            "reason": "disconnected",
        }
        self._broadcast("device", msg)

    def broadcast_touch(self, event: TouchEvent) -> None:
        """Broadcast a touch event."""
        if event.is_start:
            action = "start"
        elif event.is_end:
            action = "end"
        else:
            action = "move"

        msg = {
            "type": "touch",
            "uid": event.uid,
            "action": action,
            "index": event.touch_index,
            "x": round(event.x, 4),
            "y": round(event.y, 4),
            "z": round(event.z, 4),
            "vx": round(event.vx, 4),
            "vy": round(event.vy, 4),
            "vz": round(event.vz, 4),
        }
        self._broadcast("touch", msg)

    def broadcast_button(self, event: ButtonEvent) -> None:
        """Broadcast a button event."""
        msg = {
            "type": "button",
            "uid": event.uid,
            "action": "press" if event.is_down else "release",
        }
        self._broadcast("button", msg)

    def _broadcast(self, category: str, msg: dict[str, Any]) -> None:
        """Send message to all subscribers of the given category."""
        dead: list[int] = []
        for sub_id, sub in self._subscribers.items():
            if category in sub.events:
                try:
                    sub.queue.put_nowait(msg)
                except asyncio.QueueFull:
                    dead.append(sub_id)
                    log.debug("Client %d queue full, dropping", sub_id)

        for sub_id in dead:
            self._subscribers.pop(sub_id, None)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


class _Subscriber:
    __slots__ = ("events", "queue")

    def __init__(self, queue: asyncio.Queue[dict[str, Any]], events: set[str]) -> None:
        self.queue = queue
        self.events = events


def _device_to_dict(dev: DeviceInfo) -> dict[str, Any]:
    """Serialize DeviceInfo to the API wire format."""
    return {
        "uid": dev.uid,
        "serial": dev.serial,
        "block_type": _block_type_to_api(dev.block_type),
        "name": dev.name or dev.block_type.value,
        "battery_level": dev.battery_level,
        "battery_charging": dev.battery_charging,
        "grid_width": 15,
        "grid_height": 15,
        "firmware_version": dev.version or None,
    }


def _block_type_to_api(block_type: Any) -> str:
    """Convert BlockType enum to API string."""
    from blocksd.device.models import BlockType

    mapping = {
        BlockType.LIGHTPAD: "lightpad",
        BlockType.LIGHTPAD_M: "lightpad_m",
        BlockType.SEABOARD: "seaboard",
        BlockType.LUMI_KEYS: "lumi_keys",
        BlockType.LIVE: "live",
        BlockType.LOOP: "loop",
        BlockType.TOUCH: "touch",
        BlockType.DEV_CTRL: "developer",
        BlockType.UNKNOWN: "unknown",
    }
    return mapping.get(block_type, "unknown")
