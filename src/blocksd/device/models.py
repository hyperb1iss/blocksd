"""Data models for ROLI Blocks devices and events."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class BlockType(StrEnum):
    LIGHTPAD = "Lightpad Block"
    LIGHTPAD_M = "Lightpad Block M"
    SEABOARD = "Seaboard Block"
    LUMI_KEYS = "LUMI Keys Block"
    LIVE = "Live Block"
    LOOP = "Loop Block"
    DEV_CTRL = "Developer Control Block"
    TOUCH = "Touch Block"
    UNKNOWN = "Unknown"


@dataclass
class DeviceInfo:
    """A discovered ROLI Block device."""

    uid: int
    topology_index: int
    serial: str
    block_type: BlockType
    version: str = ""
    name: str = ""
    battery_level: int = 0
    battery_charging: bool = False
    is_master: bool = False
    master_uid: int = 0


@dataclass
class DeviceConnection:
    """A DNA connector link between two blocks."""

    device1_uid: int
    device2_uid: int
    port1: int
    port2: int


@dataclass
class Topology:
    """Current topology of connected blocks."""

    devices: list[DeviceInfo] = field(default_factory=list)
    connections: list[DeviceConnection] = field(default_factory=list)


# ── Touch / Button events ────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class TouchEvent:
    """A touch event from a pressure-sensitive surface."""

    uid: int
    timestamp: int
    touch_index: int
    x: float  # 0.0-1.0 normalized from 12-bit raw
    y: float
    z: float  # pressure, 0.0-1.0 from 8-bit raw
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    is_start: bool = False
    is_end: bool = False

    @classmethod
    def from_raw(
        cls,
        uid: int,
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
    ) -> TouchEvent:
        """Create from raw integer values (12-bit x/y, 8-bit z/velocity)."""
        return cls(
            uid=uid,
            timestamp=timestamp,
            touch_index=touch_index,
            x=x / 4095.0,
            y=y / 4095.0,
            z=z / 255.0,
            vx=(vx - 128) / 127.0 if vx else 0.0,
            vy=(vy - 128) / 127.0 if vy else 0.0,
            vz=(vz - 128) / 127.0 if vz else 0.0,
            is_start=is_start,
            is_end=is_end,
        )


@dataclass(frozen=True, slots=True)
class ButtonEvent:
    """A control button press/release event."""

    uid: int
    timestamp: int
    button_id: int
    is_down: bool


@dataclass(frozen=True, slots=True)
class ConfigValue:
    """A device configuration item with its current value and range."""

    item: int
    value: int
    min_val: int = 0
    max_val: int = 0
