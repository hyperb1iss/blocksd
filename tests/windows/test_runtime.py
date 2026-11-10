"""Portable foreground startup and Windows defaults, without MIDI hardware."""

import asyncio
import signal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from blocksd import daemon, paths
from blocksd.config import schema
from blocksd.config.presets import PresetStore


def test_windows_uses_roaming_configuration_and_websocket(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(schema, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert paths.config_paths() == [tmp_path / "blocksd/config.toml"]
    assert paths.presets_path() == tmp_path / "blocksd/presets.json"
    assert not schema.DaemonConfig().api_enabled
    assert schema.DaemonConfig().web_enabled


async def test_windows_rejects_explicit_unix_api(monkeypatch):
    monkeypatch.setattr(daemon, "sys", SimpleNamespace(platform="win32"))
    with pytest.raises(ValueError, match="local WebSocket"):
        await daemon.run_daemon(schema.DaemonConfig(api_enabled=True))


async def test_windows_foreground_signal_shutdown_restores_handlers(monkeypatch, tmp_path):
    manager = Mock()
    for name in (
        "on_device_added",
        "on_device_removed",
        "on_topology_changed",
        "on_touch_event",
        "on_button_event",
        "on_config_changed",
        "on_config_reset",
    ):
        setattr(manager, name, [])
    manager.run = AsyncMock(side_effect=asyncio.Event().wait)
    api = Mock(start=AsyncMock(), stop=AsyncMock())
    web = Mock(start=AsyncMock(), stop=AsyncMock())
    monkeypatch.setattr(daemon, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(daemon, "TopologyManager", lambda: manager)
    monkeypatch.setattr(daemon, "ApiServer", Mock(return_value=api))
    monkeypatch.setattr(daemon, "WebServer", Mock(return_value=web))
    monkeypatch.setattr(daemon, "PresetStore", lambda: PresetStore(tmp_path / "presets.json"))
    monkeypatch.setattr(daemon.sdnotify, "watchdog_usec", lambda: None)
    monkeypatch.setattr(daemon.sdnotify, "status", Mock())
    monkeypatch.setattr(daemon.sdnotify, "stopping", Mock())
    handlers = {}
    original = object()

    def install(sig, handler):
        handlers[sig] = handler
        return original

    install_mock = Mock(side_effect=install)
    monkeypatch.setattr(daemon.signal, "signal", install_mock)
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "add_signal_handler", Mock(side_effect=NotImplementedError))
    monkeypatch.setattr(
        daemon.sdnotify, "ready", lambda: handlers[signal.SIGINT](signal.SIGINT, None)
    )
    async with asyncio.timeout(2):
        await daemon.run_daemon(schema.DaemonConfig(api_enabled=False))
    manager.run.assert_awaited_once()
    api.start.assert_not_called()
    web.start.assert_awaited_once()
    web.stop.assert_awaited_once()
    assert handlers == {signal.SIGINT: original, signal.SIGTERM: original}
    assert install_mock.call_count == 4
