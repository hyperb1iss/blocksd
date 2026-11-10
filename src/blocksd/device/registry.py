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


def key_count_for_block(block_type: BlockType) -> int:
    """Return the number of independently illuminated LUMI keys."""
    return 24 if block_type == BlockType.LUMI_KEYS else 0


def supports_key_led_program(block_type: BlockType) -> bool:
    return key_count_for_block(block_type) > 0


_CONTROL_NAV = ("down", "up")

# Button functions in protocol ID order, from the SDK's BlockDataSheet.
# Firmware reports a button by its index into this list.
_BUTTON_FUNCTIONS: dict[BlockType, tuple[str, ...]] = {
    BlockType.LIGHTPAD: ("mode",),
    BlockType.LIGHTPAD_M: ("mode",),
    BlockType.SEABOARD: ("mode",),
    BlockType.LUMI_KEYS: ("mode", "down", "up"),
    BlockType.LOOP: (
        "mode",
        "volume",
        "click",
        "snap",
        "back",
        "play_or_pause",
        "record",
        "learn",
        *_CONTROL_NAV,
    ),
    BlockType.LIVE: (
        "mode",
        "volume",
        "scale",
        "chord",
        "arp",
        "sustain",
        "octave",
        "love",
        *_CONTROL_NAV,
    ),
    BlockType.DEV_CTRL: tuple(f"button{i}" for i in range(8)) + _CONTROL_NAV,
    BlockType.TOUCH: (
        "velocity_sensitivity",
        "glide_sensitivity",
        "slide_sensitivity",
        "press_sensitivity",
        "lift_sensitivity",
        "fixed_velocity",
        "glide_lock",
        "piano_mode",
        *_CONTROL_NAV,
    ),
}


def button_function(block_type: BlockType, button_id: int) -> str | None:
    """Return the SDK function name for a protocol button ID, if known."""
    functions = _BUTTON_FUNCTIONS.get(block_type, ())
    return functions[button_id] if 0 <= button_id < len(functions) else None
