"""Transport-independent API command handling and per-server subscription state."""

from __future__ import annotations

import base64
import binascii
import json
import logging
import math
import time
from typing import TYPE_CHECKING, Any

from blocksd import __version__
from blocksd.api.events import (
    EVENT_OVERFLOW_MESSAGE,
    VALID_EVENTS,
    EventBroadcaster,
    _connection_to_dict,
    _device_to_dict,
)
from blocksd.api.protocol import PIXEL_DATA_SIZE, decode_json, parse_binary_frame
from blocksd.device.registry import key_count_for_block, supports_key_led_program
from blocksd.device.settings import config_value_dict, setting_schema
from blocksd.led.bitmap import Color, LEDGrid

if TYPE_CHECKING:
    import asyncio

    from blocksd.config.presets import PresetService
    from blocksd.topology.manager import TopologyManager

log = logging.getLogger(__name__)


class ApiCommands:
    """One command implementation shared by Unix and WebSocket transports."""

    def __init__(
        self,
        manager: TopologyManager,
        *,
        presets: PresetService | None = None,
        web_url: str | None = None,
    ) -> None:
        self._manager = manager
        self._presets = presets
        self._web_url = web_url
        self._broadcaster = EventBroadcaster()
        self._start_time = time.monotonic()
        self._brightness_store: dict[int, int] = {}

    def _handle_binary_frame(self, data: bytes) -> bool:
        """Process a binary frame write. Returns True if accepted."""
        try:
            frame = parse_binary_frame(data)
        except ValueError:
            log.debug("Malformed binary frame")
            return False

        return self._write_rgb888_frame(frame.uid, frame.pixels)

    def _handle_json(
        self,
        line: bytes,
        event_queue: asyncio.Queue[dict[str, Any]],
        current_sub_id: int | None,
    ) -> tuple[dict[str, Any] | None, int | None]:
        """Process a JSON request. Returns (response, new_sub_id_or_None)."""
        try:
            msg = decode_json(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"type": "error", "message": "malformed JSON"}, None

        if not isinstance(msg, dict):
            return {"type": "error", "message": "expected JSON object"}, None
        try:
            response, sub_id = self._dispatch_message(msg, event_queue, current_sub_id)
        except (TypeError, ValueError, OSError) as error:
            response, sub_id = {"type": "error", "message": str(error)}, None
        if response is not None and "id" in msg:
            response.setdefault("id", msg["id"])
        return response, sub_id

    def _dispatch_message(
        self,
        msg: dict[str, Any],
        event_queue: asyncio.Queue[dict[str, Any]],
        current_sub_id: int | None,
    ) -> tuple[dict[str, Any] | None, int | None]:
        """Validate values at each command's own compatibility boundary."""
        if msg.get("type") == "subscribe":
            events = msg.get("events", [])
            if not isinstance(events, list) or any(not isinstance(e, str) for e in events):
                return {"type": "error", "message": "events must be a list of strings"}, None

        msg_type = msg.get("type", "")
        msg_id = msg.get("id")

        if msg_type == "ping":
            return self._handle_ping(msg_id), None

        if msg_type == "discover":
            return self._handle_discover(msg_id), None

        if msg_type == "frame":
            return self._handle_json_frame(msg), None

        if msg_type == "key_frame":
            return self._handle_json_frame(msg, key_frame=True), None

        if msg_type == "brightness":
            return self._handle_brightness(msg), None

        if msg_type == "config_get":
            return self._handle_config_get(msg), None

        if msg_type == "config_set":
            return self._handle_config_set(msg), None

        if isinstance(msg_type, str) and msg_type.startswith("preset_"):
            return self._handle_preset(msg), None

        if msg_type == "topology":
            return self._handle_topology(msg_id), None

        if msg_type == "subscribe":
            if self._broadcaster.is_closed(event_queue):
                return {"type": "error", "message": EVENT_OVERFLOW_MESSAGE}, None
            valid_events = {event for event in msg.get("events", []) if event in VALID_EVENTS}
            sub_id = self._broadcaster.subscribe(event_queue, valid_events)
            if current_sub_id is not None:
                self._broadcaster.unsubscribe(current_sub_id)
            return {"type": "subscribed", "events": sorted(valid_events)}, sub_id

        return {"type": "error", "message": f"unknown type: {msg_type}"}, None

    def _handle_ping(self, msg_id: str | None) -> dict[str, Any]:
        uptime = time.monotonic() - self._start_time
        resp: dict[str, Any] = {
            "type": "pong",
            "version": __version__,
            "uptime_seconds": int(uptime),
            "device_count": len(self._manager.devices),
            "web_url": self._web_url,
        }
        if msg_id:
            resp["id"] = msg_id
        return resp

    def _handle_discover(self, msg_id: str | None) -> dict[str, Any]:
        devices = [_device_to_dict(d) for d in self._manager.devices]
        resp: dict[str, Any] = {
            "type": "discover_response",
            "devices": devices,
        }
        if msg_id:
            resp["id"] = msg_id
        return resp

    def _handle_json_frame(self, msg: dict[str, Any], *, key_frame: bool = False) -> dict[str, Any]:
        uid = msg.get("uid")
        pixels_b64 = msg.get("pixels", "")
        ack_type = "key_frame_ack" if key_frame else "frame_ack"
        if type(uid) is not int:
            return {"type": ack_type, "uid": uid if uid is not None else 0, "accepted": False}

        try:
            pixels = base64.b64decode(pixels_b64, validate=True)
        except (binascii.Error, TypeError, ValueError):
            return {"type": ack_type, "uid": uid, "accepted": False}

        writer = self._write_rgb888_key_frame if key_frame else self._write_rgb888_frame
        accepted = writer(uid, pixels)
        return {"type": ack_type, "uid": uid, "accepted": accepted}

    def _handle_brightness(self, msg: dict[str, Any]) -> dict[str, Any]:
        uid = msg.get("uid")
        value = msg.get("value", 255)
        if type(uid) is not int:
            return {"type": "brightness_ack", "uid": uid if uid is not None else 0, "ok": False}
        if not isinstance(value, (int, float)) or (
            isinstance(value, float) and not math.isfinite(value)
        ):
            return {"type": "brightness_ack", "uid": uid, "ok": False}

        # Normalize fractional brightness before RGB565 conversion uses bit shifts.
        self._brightness_map[uid] = int(max(0, min(255, value)))
        return {"type": "brightness_ack", "uid": uid, "ok": True}

    @property
    def _brightness_map(self) -> dict[int, int]:
        return self._brightness_store

    def _write_rgb888_frame(self, uid: int, pixels: bytes) -> bool:
        """Convert RGB888 frame to RGB565 and write to device heap."""
        if len(pixels) != PIXEL_DATA_SIZE:
            return False

        device = self._manager.find_device(uid)
        if device is None:
            return False

        grid = self._rgb888_grid(uid, pixels, cols=15, rows=15)
        return self._manager.set_led_data(uid, grid.heap_data)

    def _write_rgb888_key_frame(self, uid: int, pixels: bytes) -> bool:
        """Write one RGB888 color per physical key on a supported keyboard."""
        device = self._manager.find_device(uid)
        if device is None or not supports_key_led_program(device.block_type):
            return False

        key_count = key_count_for_block(device.block_type)
        if len(pixels) != key_count * 3:
            return False

        grid = self._rgb888_grid(uid, pixels, cols=key_count, rows=1)
        return self._manager.set_key_led_data(uid, grid.heap_data)

    def _rgb888_grid(self, uid: int, pixels: bytes, *, cols: int, rows: int) -> LEDGrid:
        brightness = self._brightness_map.get(uid, 255)
        grid = LEDGrid(cols=cols, rows=rows)
        for i in range(cols * rows):
            offset = i * 3
            r, g, b = pixels[offset], pixels[offset + 1], pixels[offset + 2]

            # Apply brightness scaling
            if brightness < 255:
                r = (r * brightness) // 255
                g = (g * brightness) // 255
                b = (b * brightness) // 255

            x = i % cols
            y = i // cols
            grid.set_pixel(x, y, Color(r, g, b))
        return grid

    def _handle_config_get(self, msg: dict[str, Any]) -> dict[str, Any]:
        uid = self._target_uid(msg)
        msg_id = msg.get("id")
        device = self._manager.find_device(uid)
        refresh = msg.get("refresh", False)
        if type(refresh) is not bool:
            raise ValueError("refresh must be a boolean")
        if refresh:
            if device is None:
                raise ValueError("Device is not connected")
            if not self._manager.request_config_sync(uid):
                raise OSError("Could not request settings; device is not ready or MIDI send failed")

        values = self._manager.get_config(uid)
        resp: dict[str, Any] = {
            "type": "config_values",
            "uid": uid,
            "serial": device.serial if device else None,
            "values": [config_value_dict(cv) for cv in values.values()],
            "schema": setting_schema(list(values)),
        }
        if msg_id:
            resp["id"] = msg_id
        return resp

    def _handle_config_set(self, msg: dict[str, Any]) -> dict[str, Any]:
        uid = self._target_uid(msg)
        item = msg.get("item")
        value = msg.get("value")
        msg_id = msg.get("id")
        if uid is None or item is None or value is None:
            return {"type": "error", "message": "missing uid/item/value"}

        if type(uid) is not int:
            return {"type": "error", "message": "uid must be an integer"}
        for number in (item, value):
            if isinstance(number, bool) or (isinstance(number, float) and not number.is_integer()):
                raise ValueError("item/value must be whole integers, not booleans or fractions")
        try:
            config_item, config_value = int(item), int(value)
        except (TypeError, ValueError, OverflowError):
            return {"type": "error", "message": "item/value must be convertible to integers"}

        ok = self._manager.set_config(uid, config_item, config_value)
        device = self._manager.find_device(uid)
        resp: dict[str, Any] = {
            "type": "config_ack",
            "uid": uid,
            "item": item,
            "value": config_value,
            "serial": device.serial if device else None,
            "ok": ok,
            "status": "pending" if ok else "error",
        }
        if not ok:
            resp["message"] = (
                "Setting write or readback request failed. Check the connection and reported range, then read device state before retrying."
            )
        if msg_id:
            resp["id"] = msg_id
        return resp

    def _target_uid(self, msg: dict[str, Any]) -> int:
        if "serial" in msg:
            serial = msg["serial"]
            if not isinstance(serial, str) or not serial:
                raise ValueError("serial must be a nonempty string")
            for device in self._manager.devices:
                if device.serial == serial:
                    return device.uid
            raise ValueError("Device is not connected")
        uid = msg.get("uid")
        if type(uid) is not int:
            raise ValueError("uid must be an integer, or provide a device serial")
        return uid

    def _handle_preset(self, msg: dict[str, Any]) -> dict[str, Any]:
        service = self._presets
        if service is None:
            raise ValueError("Preset service is unavailable")
        command = msg["type"]
        if command == "preset_list":
            serial = msg.get("serial")
            if serial is not None and not isinstance(serial, str):
                raise ValueError("serial must be a string")
            return {
                "type": "preset_list",
                "presets": [p.model_dump() for p in service.store.list_presets(serial)],
            }
        if command == "preset_save":
            name = msg.get("name")
            auto_restore = msg.get("auto_restore", False)
            if not isinstance(name, str) or type(auto_restore) is not bool:
                raise ValueError("name must be a string and auto_restore must be a boolean")
            uid = self._target_uid(msg)
            preset = service.save(uid, name, auto_restore=auto_restore)
            skipped = sorted(set(self._manager.get_config(uid)) - {v.item for v in preset.values})
            return {"type": "preset_saved", "preset": preset.model_dump(), "skipped_items": skipped}
        if command == "preset_import":
            preset = service.import_preset(msg.get("preset"))
            return {"type": "preset_saved", "preset": preset.model_dump()}
        preset_id = msg.get("preset_id")
        if not isinstance(preset_id, str):
            raise TypeError("preset_id must be a string")
        if command == "preset_apply":
            uid = self._target_uid(msg)
            values = service.apply(uid, preset_id)
            return {
                "type": "preset_applied",
                "uid": uid,
                "preset_id": preset_id,
                "status": "pending",
                "values": [v.model_dump() for v in values],
            }
        if command == "preset_delete":
            service.store.delete(preset_id)
            return {"type": "preset_deleted", "preset_id": preset_id}
        if command == "preset_export":
            return {"type": "preset_export", "preset": service.store.get(preset_id).model_dump()}
        if command == "preset_update":
            auto_restore = msg.get("auto_restore")
            if type(auto_restore) is not bool:
                raise ValueError("auto_restore must be a boolean")
            preset = service.update(preset_id, auto_restore=auto_restore)
            return {"type": "preset_saved", "preset": preset.model_dump()}
        raise ValueError(f"Unknown preset command: {command}")

    def _handle_topology(self, msg_id: str | None) -> dict[str, Any]:
        devices = [_device_to_dict(d) for d in self._manager.devices]
        connections: list[dict[str, Any]] = []
        for group in self._manager.groups:
            connections.extend(_connection_to_dict(c) for c in group.topology.connections)

        resp: dict[str, Any] = {
            "type": "topology_response",
            "devices": devices,
            "connections": connections,
        }
        if msg_id:
            resp["id"] = msg_id
        return resp
