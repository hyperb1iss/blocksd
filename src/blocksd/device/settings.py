"""System setting descriptions and validation against device-reported ranges."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict

from blocksd.device.config_ids import BlockConfigId

if TYPE_CHECKING:
    from blocksd.device.models import ConfigValue


_GROUPS = {
    "MIDI": {
        BlockConfigId.MIDI_START_CHANNEL,
        BlockConfigId.MIDI_END_CHANNEL,
        BlockConfigId.MIDI_USE_MPE,
        BlockConfigId.PITCHBEND_RANGE,
        BlockConfigId.SLIDE_CC,
        BlockConfigId.SLIDE_MODE,
        BlockConfigId.MIDI_CHANNEL_RANGE,
        BlockConfigId.MPE_ZONE,
        BlockConfigId.KEY_PITCH_BEND_AMOUNT,
    },
    "Response": {
        BlockConfigId.VELOCITY_SENSITIVITY,
        BlockConfigId.GLIDE_SENSITIVITY,
        BlockConfigId.SLIDE_SENSITIVITY,
        BlockConfigId.PRESSURE_SENSITIVITY,
        BlockConfigId.LIFT_SENSITIVITY,
        BlockConfigId.FIXED_VELOCITY,
        BlockConfigId.FIXED_VELOCITY_VALUE,
        BlockConfigId.PIANO_MODE,
        BlockConfigId.GLIDE_LOCK_RATE,
        BlockConfigId.GLIDE_LOCK_ENABLED,
        BlockConfigId.X_TRACKING_MODE,
        BlockConfigId.Y_TRACKING_MODE,
        BlockConfigId.Z_TRACKING_MODE,
    },
    "Lighting": {
        BlockConfigId.GAMMA_CORRECTION,
        BlockConfigId.GLOBAL_KEY_COLOUR,
        BlockConfigId.ROOT_KEY_COLOUR,
        BlockConfigId.BRIGHTNESS,
    },
}
_LABELS = {
    BlockConfigId.MIDI_START_CHANNEL: "MIDI start channel",
    BlockConfigId.MIDI_END_CHANNEL: "MIDI end channel",
    BlockConfigId.MIDI_USE_MPE: "MIDI mode",
    BlockConfigId.MIDI_CHANNEL_RANGE: "MIDI channel range",
    BlockConfigId.PITCHBEND_RANGE: "Pitch bend range",
    BlockConfigId.MPE_ZONE: "MPE zone",
    BlockConfigId.SLIDE_CC: "Slide CC",
    BlockConfigId.ARP_PATTERN: "Arpeggiator pattern",
    BlockConfigId.X_TRACKING_MODE: "X tracking mode",
    BlockConfigId.Y_TRACKING_MODE: "Y tracking mode",
    BlockConfigId.Z_TRACKING_MODE: "Z tracking mode",
}

# ROLI SDK roli_BlockConfigManager.h defaultConfig. Ranges still come from hardware.
_OPTIONS = {
    BlockConfigId.MIDI_USE_MPE: ("Multi channel", "MPE", "Single channel"),
    BlockConfigId.MPE_ZONE: ("Lower zone", "Upper zone"),
    BlockConfigId.SLIDE_MODE: ("Absolute", "Relative unipolar", "Relative bipolar"),
    BlockConfigId.KEY: ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"),
}
_TOGGLES = {
    BlockConfigId.FIXED_VELOCITY,
    BlockConfigId.PIANO_MODE,
    BlockConfigId.GLIDE_LOCK_ENABLED,
    BlockConfigId.HIDE_MODE,
    BlockConfigId.AUTO_TRANSPOSE_TO_KEY,
}


class SettingOption(TypedDict):
    value: int
    label: str


class SettingDescription(TypedDict):
    item: int
    key: str
    label: str
    group: str
    kind: Literal["integer", "options", "toggle"]
    options: NotRequired[list[SettingOption]]


def setting_schema(items: list[int]) -> list[SettingDescription]:
    """Describe observed settings without inventing program-specific enums."""
    result: list[SettingDescription] = []
    for item in sorted(items):
        try:
            setting = BlockConfigId(item)
        except ValueError:
            key = f"setting_{item}"
            label = f"Setting {item}"
            group = "Program"
        else:
            key = setting.name.lower()
            label = _LABELS.get(setting, key.replace("_", " ").capitalize())
            group = next((name for name, ids in _GROUPS.items() if item in ids), "Musical")
        description: SettingDescription = {
            "item": item,
            "key": key,
            "label": label,
            "group": group,
            "kind": "integer",
        }
        if item in _OPTIONS:
            description["kind"] = "options"
            description["options"] = [
                {"value": value, "label": label}
                for value, label in enumerate(_OPTIONS[BlockConfigId(item)])
            ]
        elif item in _TOGGLES:
            description["kind"] = "toggle"
        result.append(description)
    return result


def config_value_dict(value: ConfigValue) -> dict[str, int | bool]:
    """Expose the observed value and whether its write range is known."""
    return {
        "item": value.item,
        "value": value.value,
        "min": value.min_val,
        "max": value.max_val,
        "writable": value.has_range and value.min_val <= value.max_val,
    }


def validate_setting(values: dict[int, ConfigValue], item: int, value: int) -> None:
    """Require an exact integer inside the device's advertised setting range."""
    if (
        type(item) is not int
        or not 0 <= item <= 255
        or type(value) is not int
        or not -(2**31) <= value < 2**31
    ):
        raise ValueError("Setting ID and value must be integers within the protocol range")
    current = values.get(item)
    if current is None or not current.has_range:
        raise ValueError(f"Setting {item} has not reported a writable range")
    if not current.min_val <= value <= current.max_val:
        raise ValueError(f"Setting {item} must be between {current.min_val} and {current.max_val}")
