"""Tests for touch, button, and config event models."""

from __future__ import annotations

import pytest

from blocksd.device.models import BlockType, ButtonEvent, ConfigValue, TouchEvent
from blocksd.device.registry import button_function


class TestTouchEvent:
    def test_from_raw_normalizes_xy(self):
        event = TouchEvent.from_raw(1, 0, 0, 2048, 2048, 128, 0, 0, 0, True, False)
        assert 0.49 < event.x < 0.51
        assert 0.49 < event.y < 0.51

    def test_from_raw_zero(self):
        event = TouchEvent.from_raw(1, 0, 0, 0, 0, 0, 0, 0, 0, False, False)
        assert event.x == 0.0
        assert event.y == 0.0
        assert event.z == 0.0

    def test_from_raw_max(self):
        event = TouchEvent.from_raw(1, 0, 0, 4095, 4095, 255, 0, 0, 0, False, True)
        assert event.x == 1.0
        assert event.y == 1.0
        assert event.z == 1.0

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # Golden values from the SDK's toBipolarFloat: (int32)(raw << 24) / 2^31.
            (0x00, 0.0),
            (0x01, 1 / 128),
            (0x40, 0.5),
            (0x7F, 127 / 128),
            (0x80, -1.0),
            (0xC0, -0.5),
            (0xFF, -1 / 128),
        ],
    )
    def test_from_raw_velocity_is_signed_8bit(self, raw: int, expected: float):
        event = TouchEvent.from_raw(1, 0, 0, 0, 0, 0, raw, raw, raw, False, False)
        assert (event.vx, event.vy, event.vz) == (expected, expected, expected)

    def test_is_start(self):
        event = TouchEvent.from_raw(1, 100, 3, 0, 0, 0, 0, 0, 0, True, False)
        assert event.is_start
        assert not event.is_end
        assert event.timestamp == 100
        assert event.touch_index == 3

    def test_is_end(self):
        event = TouchEvent.from_raw(1, 200, 0, 0, 0, 0, 0, 0, 0, False, True)
        assert not event.is_start
        assert event.is_end

    def test_frozen(self):
        event = TouchEvent.from_raw(1, 0, 0, 0, 0, 0, 0, 0, 0, False, False)
        with pytest.raises(AttributeError):
            event.__setattr__("x", 0.5)


class TestButtonEvent:
    def test_basic(self):
        event = ButtonEvent(uid=42, timestamp=1000, button_id=5, is_down=True)
        assert event.uid == 42
        assert event.button_id == 5
        assert event.is_down

    def test_frozen(self):
        event = ButtonEvent(uid=1, timestamp=0, button_id=0, is_down=False)
        with pytest.raises(AttributeError):
            event.__setattr__("is_down", True)


class TestButtonFunction:
    @pytest.mark.parametrize(
        ("block_type", "button_id", "expected"),
        [
            (BlockType.LUMI_KEYS, 0, "mode"),
            (BlockType.LUMI_KEYS, 1, "down"),
            (BlockType.LUMI_KEYS, 2, "up"),
            (BlockType.LIGHTPAD_M, 0, "mode"),
            (BlockType.LOOP, 5, "play_or_pause"),
            (BlockType.DEV_CTRL, 7, "button7"),
            (BlockType.TOUCH, 9, "up"),
        ],
    )
    def test_matches_sdk_button_order(
        self, block_type: BlockType, button_id: int, expected: str
    ) -> None:
        assert button_function(block_type, button_id) == expected

    @pytest.mark.parametrize(
        ("block_type", "button_id"),
        [(BlockType.LUMI_KEYS, 3), (BlockType.LUMI_KEYS, -1), (BlockType.UNKNOWN, 0)],
    )
    def test_unknown_ids_have_no_function(self, block_type: BlockType, button_id: int) -> None:
        assert button_function(block_type, button_id) is None


class TestConfigValue:
    def test_basic(self):
        cv = ConfigValue(item=10, value=50, min_val=0, max_val=100)
        assert cv.item == 10
        assert cv.value == 50
        assert cv.min_val == 0
        assert cv.max_val == 100

    def test_defaults(self):
        cv = ConfigValue(item=5, value=42)
        assert cv.min_val == 0
        assert cv.max_val == 0
