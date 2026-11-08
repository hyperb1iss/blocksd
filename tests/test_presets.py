"""Preset persistence, validated device writes, and reconnect behavior."""

import asyncio
import json
from unittest.mock import Mock

import pytest

from blocksd.api.server import ApiServer, WebServer
from blocksd.config.presets import PresetService, PresetStore
from blocksd.device.models import BlockType, ConfigValue, DeviceInfo, Topology
from blocksd.device.settings import validate_setting
from blocksd.topology.device_group import DeviceGroup
from blocksd.topology.manager import TopologyManager


class ConnectedManager(TopologyManager):
    """Observations arrive separately from writes, like physical MIDI."""

    def __init__(self):
        super().__init__()
        self.device = DeviceInfo(2**63 + 17, 0, "LKB0123456789ABC", BlockType.LUMI_KEYS)
        self.values = {
            2: ConfigValue(2, 1, 0, 2, has_range=True),
            5: ConfigValue(5, -2, -11, 11, has_range=True),
        }
        self.sent = []
        self.send_ok = True
        self.connected = True
        self.connection = self._new_connection()

    def _new_connection(self):
        connection = DeviceGroup(Mock())
        connection.topology = Topology(devices=[self.device])
        return connection

    @property
    def groups(self):
        return [self.connection] if self.connected else []

    @property
    def devices(self):
        return [self.device] if self.connected else []

    def find_device(self, uid):
        return self.device if self.connected and uid == self.device.uid else None

    def get_config(self, uid):
        return dict(self.values) if self.find_device(uid) else {}

    def set_config(self, uid, item, value):
        validate_setting(self.get_config(uid), item, value)
        if self.send_ok:
            self.sent.append((item, value))
        return self.send_ok

    def observe(self, config):
        self.values[config.item] = config
        for callback in self.on_config_changed:
            callback(self.device.uid, config)

    def disconnect(self, *, physical=True):
        self.connected = False
        self.values.clear()
        for callback in self.on_device_removed:
            callback(self.device)
        if physical:
            self.connection = self._new_connection()


@pytest.fixture
def runtime(tmp_path):
    manager = ConnectedManager()
    store = PresetStore(tmp_path / "presets.json")
    service = PresetService(manager, store)
    service.start()
    yield manager, service
    service.close()
    assert not manager.on_config_changed
    assert not manager.on_device_removed


def test_save_roundtrip_and_only_observed_settings(runtime):
    manager, service = runtime
    manager.values[80] = ConfigValue(80, 100)
    preset = service.save(manager.device.uid, "  soft keys  ", auto_restore=True)
    loaded = PresetStore(service.store.path).get(preset.id)
    assert loaded == preset
    assert loaded.name == "soft keys"
    assert [(v.item, v.value) for v in loaded.values] == [(2, 1), (5, -2)]
    assert service.store.path.stat().st_mode & 0o777 == 0o600
    assert not manager.sent


def test_write_failure_preserves_prior_file_and_memory(runtime, monkeypatch):
    manager, service = runtime
    preset = service.save(manager.device.uid, "original")
    original = service.store.path.read_bytes()
    monkeypatch.setattr(
        "blocksd.config.presets.os.replace", Mock(side_effect=OSError("disk failure"))
    )
    with pytest.raises(OSError, match="disk failure"):
        service.store.delete(preset.id)
    assert service.store.path.read_bytes() == original
    assert service.store.get(preset.id) == preset
    assert list(service.store.path.parent.glob(".presets-*")) == []


def test_corrupt_file_is_not_silently_replaced(tmp_path):
    path = tmp_path / "presets.json"
    path.write_text("broken")
    with pytest.raises(ValueError):
        PresetStore(path)
    assert path.read_text() == "broken"


def test_apply_validates_every_value_before_writing(runtime):
    manager, service = runtime
    preset = service.save(manager.device.uid, "keyboard")
    manager.values[5] = ConfigValue(5, 0, 0, 11, has_range=True)
    with pytest.raises(ValueError, match="between"):
        service.apply(manager.device.uid, preset.id)
    assert manager.sent == []


def test_apply_requires_matching_serial_and_family(runtime):
    manager, service = runtime
    preset = service.save(manager.device.uid, "keyboard")
    manager.device.serial = "another block"
    with pytest.raises(ValueError, match="different device"):
        service.apply(manager.device.uid, preset.id)
    manager.device.serial = preset.serial
    manager.device.block_type = BlockType.SEABOARD
    with pytest.raises(ValueError, match="different device"):
        service.apply(manager.device.uid, preset.id)
    assert not manager.sent


def test_partial_apply_reports_the_successful_prefix(runtime, monkeypatch):
    manager, service = runtime
    preset = service.save(manager.device.uid, "keyboard")
    monkeypatch.setattr(manager, "set_config", Mock(side_effect=[True, False]))
    with pytest.raises(ValueError, match=r"completed setting requests \[2\]"):
        service.apply(manager.device.uid, preset.id)


def test_reconnect_restore_waits_for_ranges_and_runs_once(runtime):
    manager, service = runtime
    service.save(manager.device.uid, "show", auto_restore=True)
    manager.observe(ConfigValue(2, 2, 0, 2, has_range=True))
    assert not manager.sent  # Enabling reconnect restore does not apply immediately.
    manager.disconnect()
    manager.connected = True
    manager.observe(ConfigValue(2, 2, 0, 2, has_range=True))
    manager.observe(ConfigValue(5, 0))
    assert not manager.sent
    manager.observe(ConfigValue(5, 0, -11, 11, has_range=True))
    assert manager.sent == [(2, 1), (5, -2)]
    assert manager.values[5].value == 0  # Sends do not fabricate device observations.
    manager.observe(ConfigValue(5, -2, -11, 11, has_range=True))
    assert len(manager.sent) == 2
    manager.disconnect()
    manager.connected = True
    manager.observe(ConfigValue(2, 2, 0, 2, has_range=True))
    manager.observe(ConfigValue(5, 0, -11, 11, has_range=True))
    assert len(manager.sent) == 4


def test_transient_rediscovery_keeps_unsaved_values_within_usb_session(runtime):
    manager, service = runtime
    service.save(manager.device.uid, "show", auto_restore=True)
    manager.disconnect(physical=False)
    manager.connected = True
    manager.observe(ConfigValue(2, 2, 0, 2, has_range=True))
    manager.observe(ConfigValue(5, 7, -11, 11, has_range=True))
    assert not manager.sent
    assert manager.values[5].value == 7
    manager.disconnect()
    manager.connected = True
    manager.observe(ConfigValue(2, 2, 0, 2, has_range=True))
    manager.observe(ConfigValue(5, 7, -11, 11, has_range=True))
    assert manager.sent == [(2, 1), (5, -2)]


def test_new_service_restores_saved_settings_after_daemon_restart(runtime):
    manager, service = runtime
    service.save(manager.device.uid, "startup", auto_restore=True)
    service.close()
    restarted = PresetService(manager, PresetStore(service.store.path))
    restarted.start()
    try:
        manager.observe(ConfigValue(5, 6, -11, 11, has_range=True))
        assert manager.sent == [(2, 1), (5, -2)]
    finally:
        restarted.close()


def test_save_excludes_bad_ranges_and_out_of_range_values(runtime, caplog):
    manager, service = runtime
    manager.values[7] = ConfigValue(7, 0, 4, 2, has_range=True)
    manager.values[8] = ConfigValue(8, 10, 0, 2, has_range=True)
    manager.values[9] = ConfigValue(9, 0)
    preset = service.save(manager.device.uid, "usable")
    assert {value.item for value in preset.values} == {2, 5}
    assert "excluded settings" in caplog.text
    assert "[7, 8, 9]" in caplog.text
    manager.values = {7: manager.values[7]}
    with pytest.raises(ValueError, match="No device-reported settings"):
        service.save(manager.device.uid, "empty")


def test_updating_preset_preserves_order_and_exclusive_restore(runtime):
    manager, service = runtime
    first = service.save(manager.device.uid, "first")
    second = service.save(manager.device.uid, "second", auto_restore=True)
    service.update(first.id, auto_restore=True)
    presets = service.store.list_presets()
    assert [preset.id for preset in presets] == [first.id, second.id]
    assert [preset.auto_restore for preset in presets] == [True, False]
    assert [preset.id for preset in PresetStore(service.store.path).list_presets()] == [
        first.id,
        second.id,
    ]


def test_only_one_restore_preset_per_device_and_import_never_arms_restore(runtime):
    manager, service = runtime
    first = service.save(manager.device.uid, "first", auto_restore=True)
    second = service.save(manager.device.uid, "second", auto_restore=True)
    assert not service.store.get(first.id).auto_restore
    assert service.store.get(second.id).auto_restore
    imported = service.import_preset(second.model_dump())
    assert imported.id != second.id
    assert not imported.auto_restore
    service.update(first.id, auto_restore=True)
    assert not service.store.get(second.id).auto_restore
    assert service.store.get(first.id).auto_restore


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("values", [{"item": 2, "value": True}]),
        ("values", []),
        ("name", " "),
        ("block_type", "unknown instrument"),
        ("auto_restore", "yes"),
    ],
)
def test_invalid_import_does_not_mutate_store(runtime, field, value):
    manager, service = runtime
    preset = service.save(manager.device.uid, "original")
    payload = preset.model_dump()
    payload[field] = value
    with pytest.raises(ValueError):
        service.import_preset(payload)
    assert service.store.list_presets() == [preset]


def request(server, **message):
    response, _ = server._handle_json(json.dumps(message).encode(), asyncio.Queue(), None)
    return response


def test_two_transports_share_presets_and_support_exact_serial_target(runtime):
    manager, service = runtime
    unix = ApiServer(manager, presets=service)
    web = WebServer(manager, presets=service)
    saved = request(
        unix, type="preset_save", serial=manager.device.serial, name="shared", id="save"
    )
    assert saved["type"] == "preset_saved" and saved["id"] == "save"
    preset_id = saved["preset"]["id"]
    listed = request(web, type="preset_list", serial=manager.device.serial)
    assert listed["presets"] == [saved["preset"]]
    applied = request(web, type="preset_apply", serial=manager.device.serial, preset_id=preset_id)
    assert applied["status"] == "pending"
    assert manager.sent == [(2, 1), (5, -2)]
    exported = request(web, type="preset_export", preset_id=preset_id)
    assert exported["preset"] == saved["preset"]
    request(web, type="preset_delete", preset_id=preset_id)
    assert request(unix, type="preset_list")["presets"] == []


def test_config_ack_is_pending_until_device_event_and_send_failure_is_error(runtime):
    manager, service = runtime
    api = ApiServer(manager, presets=service, web_url="http://localhost:9012")
    queue = asyncio.Queue()
    api._broadcaster.subscribe(queue, {"config"})
    api._attach_events()
    try:
        response = request(api, type="config_set", serial=manager.device.serial, item=5, value=3)
        assert response["ok"] and response["status"] == "pending"
        assert queue.empty() and manager.values[5].value == -2
        manager.observe(ConfigValue(5, 3, -11, 11, has_range=True))
        observed = queue.get_nowait()
        assert observed["serial"] == manager.device.serial
        assert observed["value"] == 3 and observed["writable"]
        assert observed["min"] == -11
        assert observed["schema"]["key"] == "transpose"
        manager.send_ok = False
        failed = request(api, type="config_set", serial=manager.device.serial, item=5, value=4)
        assert failed["status"] == "error" and not failed["ok"]
        assert request(api, type="ping")["web_url"] == "http://localhost:9012"
    finally:
        asyncio.run(api.stop())


def test_metadata_is_shared_and_missing_ranges_are_not_writable(runtime):
    manager, service = runtime
    manager.values[30] = ConfigValue(30, 1)
    api = ApiServer(manager, presets=service)
    response = request(api, type="config_get", serial=manager.device.serial)
    schema = {item["item"]: item for item in response["schema"]}
    assert schema[30]["key"] == "x_tracking_mode"
    assert schema[2]["options"] == [
        {"value": 0, "label": "Multi channel"},
        {"value": 1, "label": "MPE"},
        {"value": 2, "label": "Single channel"},
    ]
    assert next(value for value in response["values"] if value["item"] == 30)["writable"] is False


def test_late_reported_setting_event_supplies_selector_metadata(runtime):
    manager, service = runtime
    manager.values.clear()
    api = ApiServer(manager, presets=service)
    assert request(api, type="config_get", serial=manager.device.serial)["schema"] == []
    queue = asyncio.Queue()
    api._broadcaster.subscribe(queue, {"config"})
    api._attach_events()
    try:
        manager.observe(ConfigValue(2, 1, 0, 2, has_range=True))
        event = queue.get_nowait()
        assert event["schema"]["key"] == "midi_use_mpe"
        assert event["schema"]["kind"] == "options"
        assert event["schema"]["options"][1] == {"value": 1, "label": "MPE"}
    finally:
        asyncio.run(api.stop())


def test_api_save_reports_omitted_settings(runtime):
    manager, service = runtime
    manager.values[7] = ConfigValue(7, 0, 5, 2, has_range=True)
    manager.values[8] = ConfigValue(8, 1)
    api = ApiServer(manager, presets=service)
    response = request(api, type="preset_save", serial=manager.device.serial, name="playable")
    assert response["type"] == "preset_saved"
    assert response["skipped_items"] == [7, 8]
    assert {value["item"] for value in response["preset"]["values"]} == {2, 5}


@pytest.mark.parametrize(("item", "value"), [(True, 1), (2, True), (2.9, 1), (2, 1.2)])
def test_config_rejects_boolean_and_fractional_values(runtime, item, value):
    manager, service = runtime
    api = ApiServer(manager, presets=service)
    response = request(api, type="config_set", serial=manager.device.serial, item=item, value=value)
    assert response["type"] == "error"
    assert not manager.sent
