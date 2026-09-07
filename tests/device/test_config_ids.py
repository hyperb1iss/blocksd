"""Wire IDs checked against ROLI's system configuration declarations.

Reference: roli_blocks_basics at 212ba4e237638b9ae8c2a4f76dd2070110392031,
blocks/roli_BlockConfigId.h and littlefoot/scripts/LittleFootLibrary/ConfigIds.littlefoot.
"""

import pytest

from blocksd.device.config_ids import BlockConfigId


@pytest.mark.parametrize(
    ("name", "wire_id"),
    [
        ("MIDI_START_CHANNEL", 0),
        ("MIDI_END_CHANNEL", 1),
        ("MIDI_USE_MPE", 2),
        ("SLIDE_MODE", 7),
        ("GLIDE_SENSITIVITY", 11),
        ("SLIDE_SENSITIVITY", 12),
        ("MODE", 20),
        ("CHORD", 24),
        ("X_TRACKING_MODE", 30),
        ("Y_TRACKING_MODE", 31),
        ("Z_TRACKING_MODE", 32),
        ("GLOBAL_KEY_COLOUR", 34),
        ("ROOT_KEY_COLOUR", 35),
        ("BRIGHTNESS", 36),
        ("MPE_ZONE", 40),
        ("KEY_PITCH_BEND_AMOUNT", 41),
    ],
)
def test_system_setting_wire_id(name: str, wire_id: int):
    assert BlockConfigId[name].value == wire_id
    assert BlockConfigId(wire_id).name == name


def test_system_ids_preserve_sdk_gaps_and_exclude_user_slots():
    assert {item.value for item in BlockConfigId} == set(range(29)) | set(range(30, 37)) | {
        40,
        41,
    }


@pytest.mark.parametrize(
    "name",
    ["MIDI_CHANNEL_MODE", "GRID_SIZE", "COLOUR_PRESET", "MPE_CHANNEL_START", "MPE_CHANNEL_END"],
)
def test_misleading_names_are_not_compatibility_aliases(name: str):
    assert name not in BlockConfigId.__members__
