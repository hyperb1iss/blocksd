"""Block configuration item IDs — indices used in config get/set messages."""

from enum import IntEnum


class BlockConfigId(IntEnum):
    """Known configuration items for ROLI Blocks."""

    VELOCITY_SENSITIVITY = 10
    SLIDE_SENSITIVITY = 11
    SLIDE_CC = 6
    GLIDE_SENSITIVITY = 12
    PRESSURE_SENSITIVITY = 13
    LIFT_SENSITIVITY = 14
    PITCHBEND_RANGE = 3
    OCTAVE = 4
    TRANSPOSE = 5
    MIDI_CHANNEL_MODE = 7
    FIXED_VELOCITY = 15
    GLIDE_LOCK_RATE = 18
    GLIDE_LOCK_ENABLED = 19
    GRID_SIZE = 20
    SCALE = 22
    HIDE_MODE = 23
    COLOUR_PRESET = 24
    MPE_ZONE = 30
    MPE_CHANNEL_START = 31
    MPE_CHANNEL_END = 32
    GAMMA_CORRECTION = 33
    PIANO_MODE = 17
    FIXED_VELOCITY_VALUE = 16
