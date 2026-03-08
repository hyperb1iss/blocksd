"""Device registry — maps serial prefixes to device capabilities."""

from __future__ import annotations

from blocksd.device.models import BlockType

SERIAL_PREFIX_MAP: dict[str, BlockType] = {
    "LPB": BlockType.LIGHTPAD,
    "LPM": BlockType.LIGHTPAD_M,
    "SBB": BlockType.SEABOARD,
    "LKB": BlockType.LUMI_KEYS,
    "LIC": BlockType.LIVE,
    "LOC": BlockType.LOOP,
    "DCB": BlockType.DEV_CTRL,
    "TCB": BlockType.TOUCH,
}


def block_type_from_serial(serial: str) -> BlockType:
    """Identify block type from its serial number prefix."""
    prefix = serial[:3] if len(serial) >= 3 else ""
    return SERIAL_PREFIX_MAP.get(prefix, BlockType.UNKNOWN)


def is_pad_block(serial: str) -> bool:
    return serial[:3] in ("LPB", "LPM")


def is_seaboard_block(serial: str) -> bool:
    return serial[:3] == "SBB"


def is_control_block(serial: str) -> bool:
    return serial[:3] in ("LIC", "LOC", "DCB", "TCB")


def is_lumi_keys_block(serial: str) -> bool:
    return serial[:3] == "LKB"
