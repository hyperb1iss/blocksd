"""Group task ownership across disconnect, replacement, and shutdown."""

import asyncio
from unittest.mock import Mock

import pytest

from blocksd.topology.detector import MidiPortPair
from blocksd.topology.manager import TopologyManager

PORT = MidiPortPair(0, 0, "port").key


async def test_old_completion_preserves_replacement_group():
    manager = TopologyManager()
    old = asyncio.create_task(asyncio.sleep(0))
    await old
    replacement = asyncio.create_task(asyncio.sleep(0))
    entry = Mock()
    manager._tasks[PORT] = replacement
    manager._groups[PORT] = entry
    manager._on_group_done(PORT, old)
    assert manager._tasks[PORT] is replacement
    assert manager._groups[PORT] is entry
    await replacement


async def test_cancelled_group_callback_is_safe():
    manager = TopologyManager()
    task = asyncio.create_task(asyncio.sleep(0))
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    manager._tasks[PORT] = task
    manager._on_group_done(PORT, task)
    assert not manager._tasks


async def test_shutdown_joins_removed_group_cleanup():
    manager = TopologyManager()
    started = asyncio.Event()
    cleaned = asyncio.Event()

    async def run():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            cleaned.set()

    task = asyncio.create_task(run())
    manager._tasks[PORT] = task
    manager._running_tasks.add(task)
    await started.wait()
    manager._remove_group(PORT)
    await manager._shutdown()
    assert task.done()
    assert cleaned.is_set()


async def test_shutdown_does_not_cancel_in_progress_group_cleanup():
    manager = TopologyManager()
    started = asyncio.Event()
    cleaning = asyncio.Event()
    cleaned = asyncio.Event()

    async def run():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaning.set()
            await asyncio.sleep(0)
            cleaned.set()

    task = asyncio.create_task(run())
    manager._tasks[PORT] = task
    manager._running_tasks.add(task)
    await started.wait()
    manager._remove_group(PORT)
    await cleaning.wait()
    await manager._shutdown()
    assert cleaned.is_set()


@pytest.mark.parametrize("removed_index", [0, 1])
async def test_duplicate_names_keep_independent_groups(monkeypatch, removed_index):
    from blocksd.topology import manager as module

    pairs = [
        MidiPortPair(0, 0, "Lightpad BLOCK", (10, 20)),
        MidiPortPair(1, 1, "Lightpad BLOCK", (11, 21)),
    ]
    monkeypatch.setattr(module, "scan_for_blocks", lambda: list(pairs))

    async def run_group(_self):
        await asyncio.Event().wait()

    monkeypatch.setattr(module.DeviceGroup, "run", run_group)
    open_port = Mock(return_value=Mock())
    monkeypatch.setattr(module, "open_connection", open_port)
    manager = TopologyManager()
    try:
        await manager._scan_cycle()
        assert len(manager.groups) == 2
        assert open_port.call_count == 2
        await manager._scan_cycle()
        assert open_port.call_count == 2
        pairs.pop(removed_index)
        survivor = pairs[0]
        original_group = manager._groups[survivor.key]
        pairs[:] = [MidiPortPair(0, 0, survivor.name, survivor.endpoint_ids)]
        await manager._scan_cycle()
        assert len(manager.groups) == 1
        assert manager._groups[survivor.key] is original_group
        assert open_port.call_count == 2
    finally:
        await manager._shutdown()


@pytest.mark.parametrize("ids", [None, (10, 20)])
async def test_reindexed_port_preserves_live_handle(monkeypatch, ids):
    from blocksd.topology import manager as module

    old_pair = MidiPortPair(1, 1, "Lightpad BLOCK", ids)
    new_pair = MidiPortPair(0, 0, "Lightpad BLOCK", ids)
    pairs = [old_pair]
    closed = asyncio.Event()
    started = asyncio.Event()

    async def run_group(_self):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            closed.set()

    open_port = Mock(return_value=Mock())
    monkeypatch.setattr(module, "scan_for_blocks", lambda: list(pairs))
    monkeypatch.setattr(module, "open_connection", open_port)
    monkeypatch.setattr(module.DeviceGroup, "run", run_group)
    manager = TopologyManager()
    try:
        await manager._scan_cycle()
        await started.wait()
        original_group = manager._groups[old_pair.key]
        pairs[:] = [new_pair]
        await manager._scan_cycle()
        assert manager._groups[new_pair.key] is original_group
        assert not closed.is_set()
        assert open_port.call_count == 1
    finally:
        await manager._shutdown()
