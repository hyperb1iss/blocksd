"""Pydantic models for ROLI Blocks devices."""

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
