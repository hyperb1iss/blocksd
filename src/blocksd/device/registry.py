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


def heap_size_for_block(block_type: BlockType) -> int:
    """Return program+heap memory size for a device type.

    Pad blocks (Lightpad, Lightpad M) get the full 7200 bytes.
    Control blocks (Live, Loop, Dev, Touch) get 3000 bytes.
    LUMI Keys and Seaboard use pad block sizing.
    """
    from blocksd.protocol.constants import (
        CONTROL_BLOCK_PROGRAM_HEAP_SIZE,
        PAD_BLOCK_PROGRAM_HEAP_SIZE,
    )

    if block_type in (BlockType.LIVE, BlockType.LOOP, BlockType.DEV_CTRL, BlockType.TOUCH):
        return CONTROL_BLOCK_PROGRAM_HEAP_SIZE
    return PAD_BLOCK_PROGRAM_HEAP_SIZE


def bitmap_grid_dimensions(block_type: BlockType) -> tuple[int, int]:
    """Return the upstream LEDGrid dimensions for bitmap-addressable devices."""
    if block_type in (BlockType.LIGHTPAD, BlockType.LIGHTPAD_M):
        return (15, 15)
    return (0, 0)


def supports_bitmap_led_program(block_type: BlockType) -> bool:
    """Whether the device exposes an upstream LEDGrid-style bitmap surface."""
    return bitmap_grid_dimensions(block_type) != (0, 0)
