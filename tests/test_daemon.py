"""Daemon ownership and failure supervision without MIDI hardware."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from blocksd import daemon
from blocksd.config.schema import DaemonConfig


@pytest.fixture
async def runtime(monkeypatch):
    manager = Mock()
    for name in (
        "on_device_added",
        "on_device_removed",
        "on_topology_changed",
        "on_touch_event",
        "on_button_event",
    ):
        setattr(manager, name, [])
    manager.run = AsyncMock()
    api = Mock(start=AsyncMock(), stop=AsyncMock())
    web = Mock(start=AsyncMock(), stop=AsyncMock())
    monkeypatch.setattr(daemon, "TopologyManager", Mock(return_value=manager))
    monkeypatch.setattr(daemon, "ApiServer", Mock(return_value=api))
    monkeypatch.setattr(daemon, "WebServer", Mock(return_value=web))
    monkeypatch.setattr(daemon, "setup_logging", Mock())
    monkeypatch.setattr(daemon.sdnotify, "watchdog_usec", Mock(return_value=None))
    for name in ("ready", "status", "stopping"):
        monkeypatch.setattr(daemon.sdnotify, name, Mock())
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "add_signal_handler", Mock())
    monkeypatch.setattr(loop, "remove_signal_handler", Mock())
    return manager, api, web, loop


async def test_partial_startup_unwinds_servers_and_signals(runtime):
    _, api, web, loop = runtime
    web.start.side_effect = OSError("address in use")
    with pytest.raises(OSError, match="address in use"):
        await daemon.run_daemon(DaemonConfig())
    api.stop.assert_awaited_once()
    web.stop.assert_awaited_once()
    assert loop.remove_signal_handler.call_count == 2


async def test_shutdown_accepts_watchdog_completion(runtime, monkeypatch):
    manager, api, web, loop = runtime
    manager.run.side_effect = asyncio.Event().wait
    monkeypatch.setattr(daemon.sdnotify, "watchdog_usec", Mock(return_value=1_000_000))
    monkeypatch.setattr(daemon.sdnotify, "watchdog", Mock())
    # A signal before the first heartbeat lets both shutdown tasks complete together.
    monkeypatch.setattr(
        daemon.sdnotify,
        "ready",
        Mock(side_effect=lambda: loop.add_signal_handler.call_args.args[1]()),
    )
    async with asyncio.timeout(2):
        await daemon.run_daemon(DaemonConfig())
    api.stop.assert_awaited_once()
    web.stop.assert_awaited_once()


async def test_shutdown_does_not_hide_manager_failure(runtime, monkeypatch):
    manager, _, _, loop = runtime
    manager.run.side_effect = RuntimeError("scan failed")
    monkeypatch.setattr(
        daemon.sdnotify,
        "ready",
        Mock(side_effect=lambda: loop.add_signal_handler.call_args.args[1]()),
    )
    with pytest.raises(RuntimeError, match="scan failed"):
        await daemon.run_daemon(DaemonConfig())
    assert loop.remove_signal_handler.call_count == 2


@pytest.mark.parametrize("failure", [RuntimeError("scan failed"), None])
async def test_manager_exit_is_supervised(runtime, failure):
    manager, api, web, _ = runtime
    manager.run.side_effect = failure
    with pytest.raises(RuntimeError, match=r"scan failed|stopped unexpectedly"):
        async with asyncio.timeout(2):
            await daemon.run_daemon(DaemonConfig())
    api.stop.assert_awaited_once()
    web.stop.assert_awaited_once()


async def test_cancellation_joins_manager_and_releases_servers(runtime):
    manager, api, web, _ = runtime
    started = asyncio.Event()
    cleaned = asyncio.Event()

    async def run():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    manager.run.side_effect = run
    task = asyncio.create_task(daemon.run_daemon(DaemonConfig()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned.is_set()
    api.stop.assert_awaited_once()
    web.stop.assert_awaited_once()
