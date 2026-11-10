"""Named device snapshots, atomic persistence, and opt-in reconnect restore."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from blocksd.device.models import BlockType
from blocksd.device.settings import validate_setting
from blocksd.paths import presets_path

if TYPE_CHECKING:
    from blocksd.device.models import ConfigValue, DeviceInfo
    from blocksd.topology.device_group import DeviceGroup
    from blocksd.topology.manager import TopologyManager

log = logging.getLogger(__name__)


class PresetValue(BaseModel):
    """One observed integer setting, independent of its current range."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    item: int = Field(ge=0, le=255)
    value: int = Field(ge=-(2**31), le=2**31 - 1)


class Preset(BaseModel):
    """A snapshot belongs to one physical device, identified by serial."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    serial: str = Field(min_length=1, max_length=100)
    block_type: str
    values: list[PresetValue] = Field(min_length=1, max_length=256)
    auto_restore: bool = False

    @field_validator("name", "serial", "id")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Must not be blank")
        return value.strip()

    @field_validator("block_type")
    @classmethod
    def known_type(cls, value: str) -> str:
        BlockType(value)
        return value

    @model_validator(mode="after")
    def unique_items(self) -> Preset:
        if len({value.item for value in self.values}) != len(self.values):
            raise ValueError("Preset contains duplicate setting IDs")
        return self


class PresetDocument(BaseModel):
    """Versioned on-disk document; invalid files are never silently replaced."""

    model_config = ConfigDict(extra="forbid", strict=True)
    version: Literal[1] = 1
    presets: list[Preset] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_presets(self) -> PresetDocument:
        if len({preset.id for preset in self.presets}) != len(self.presets):
            raise ValueError("Preset IDs must be unique")
        restored = [preset.serial for preset in self.presets if preset.auto_restore]
        if len(set(restored)) != len(restored):
            raise ValueError("Only one reconnect preset is allowed per device")
        return self


class PresetStore:
    """One daemon owns one store shared by every API transport."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else presets_path()
        self._document = (
            PresetDocument.model_validate_json(self.path.read_text(encoding="utf-8"))
            if self.path.exists()
            else PresetDocument()
        )

    def list_presets(self, serial: str | None = None) -> list[Preset]:
        return [p for p in self._document.presets if serial is None or p.serial == serial]

    def get(self, preset_id: str) -> Preset:
        for preset in self._document.presets:
            if preset.id == preset_id:
                return preset
        raise ValueError("Preset not found")

    def put(self, preset: Preset) -> Preset:
        presets = [preset if p.id == preset.id else p for p in self._document.presets]
        if not any(p.id == preset.id for p in self._document.presets):
            presets.append(preset)
        if preset.auto_restore:
            presets = [
                p.model_copy(update={"auto_restore": False})
                if p.serial == preset.serial and p.id != preset.id
                else p
                for p in presets
            ]
        self._write(PresetDocument(presets=presets))
        return preset

    def delete(self, preset_id: str) -> None:
        self.get(preset_id)
        self._write(
            PresetDocument(presets=[p for p in self._document.presets if p.id != preset_id])
        )

    def _write(self, document: PresetDocument) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=".presets-",
                suffix=".json",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(document.model_dump_json(indent=2) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self._document = document


class PresetService:
    """Apply snapshots only after the matching device reports every range."""

    def __init__(self, manager: TopologyManager, store: PresetStore) -> None:
        self.manager = manager
        self.store = store
        self._restore_attempted: dict[int, DeviceGroup] = {}
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self.manager.on_config_changed.append(self._on_config)
        self._started = True

    def close(self) -> None:
        if self._started:
            self.manager.on_config_changed.remove(self._on_config)
            self._started = False
        self._restore_attempted.clear()

    def save(self, uid: int, name: str, *, auto_restore: bool = False) -> Preset:
        device = self._device(uid)
        values = self.manager.get_config(uid)
        observed = []
        skipped = []
        for value in values.values():
            try:
                validate_setting(values, value.item, value.value)
            except ValueError:
                skipped.append(value.item)
            else:
                observed.append(PresetValue(item=value.item, value=value.value))
        if not observed:
            raise ValueError("No device-reported settings are available to save")
        preset = self.store.put(
            Preset(
                id=str(uuid4()),
                name=name,
                serial=device.serial,
                block_type=device.block_type.value,
                values=sorted(observed, key=lambda value: value.item),
                auto_restore=auto_restore,
            )
        )
        if skipped:
            log.warning(
                "Preset %s excluded settings without valid writable values: %s",
                preset.name,
                skipped,
            )
        self._mark_attempted(uid)
        return preset

    def apply(self, uid: int, preset_id: str) -> list[PresetValue]:
        device = self._device(uid)
        preset = self.store.get(preset_id)
        if preset.serial != device.serial or preset.block_type != device.block_type.value:
            raise ValueError("Preset belongs to a different device")
        values = self.manager.get_config(uid)
        for value in preset.values:
            validate_setting(values, value.item, value.value)
        self._mark_attempted(uid)
        sent: list[int] = []
        for value in preset.values:
            if not self.manager.set_config(uid, value.item, value.value):
                raise ValueError(
                    f"Write or readback request failed for setting {value.item}; completed setting requests {sent}. Device state may be partially changed. Read back before retrying."
                )
            sent.append(value.item)
        return preset.values

    def import_preset(self, payload: object) -> Preset:
        preset = Preset.model_validate(payload)
        return self.store.put(preset.model_copy(update={"id": str(uuid4()), "auto_restore": False}))

    def update(self, preset_id: str, *, auto_restore: bool) -> Preset:
        if type(auto_restore) is not bool:
            raise ValueError("auto_restore must be a boolean")
        preset = self.store.put(
            self.store.get(preset_id).model_copy(update={"auto_restore": auto_restore})
        )
        for device in self.manager.devices:
            if device.serial == preset.serial:
                self._mark_attempted(device.uid)
        return preset

    def _device(self, uid: int) -> DeviceInfo:
        device = self.manager.find_device(uid)
        if device is None:
            raise ValueError("Device is not connected")
        return device

    def _connection_session(self, uid: int) -> DeviceGroup | None:
        return next(
            (
                group
                for group in self.manager.groups
                if any(device.uid == uid for device in group.topology.devices)
            ),
            None,
        )

    def _mark_attempted(self, uid: int) -> None:
        if group := self._connection_session(uid):
            self._restore_attempted[uid] = group

    def _on_config(self, uid: int, _value: ConfigValue) -> None:
        group = self._connection_session(uid)
        if group is None or self._restore_attempted.get(uid) is group:
            return
        device = self.manager.find_device(uid)
        if device is None:
            return
        preset = next((p for p in self.store.list_presets(device.serial) if p.auto_restore), None)
        if preset is None:
            return
        values = self.manager.get_config(uid)
        if any(v.item not in values or not values[v.item].has_range for v in preset.values):
            return
        self._restore_attempted[uid] = group
        try:
            self.apply(uid, preset.id)
        except ValueError:
            log.exception("Reconnect preset %s could not be sent to %s", preset.name, device.serial)
        else:
            log.info(
                "Reconnect preset %s sent to %s; device readback pending",
                preset.name,
                device.serial,
            )
