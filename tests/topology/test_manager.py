"""Group task ownership across disconnect, replacement, and shutdown."""

import asyncio
from unittest.mock import Mock

from blocksd.topology.manager import TopologyManager


async def test_old_completion_preserves_replacement_group():
    manager = TopologyManager()
    old = asyncio.create_task(asyncio.sleep(0))
    await old
    replacement = asyncio.create_task(asyncio.sleep(0))
    entry = Mock()
    manager._tasks["port"] = replacement
    manager._groups["port"] = entry
    manager._on_group_done("port", old)
    assert manager._tasks["port"] is replacement
    assert manager._groups["port"] is entry
    await replacement


async def test_cancelled_group_callback_is_safe():
    manager = TopologyManager()
    task = asyncio.create_task(asyncio.sleep(0))
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    manager._tasks["port"] = task
    manager._on_group_done("port", task)
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
    manager._tasks["port"] = task
    manager._running_tasks.add(task)
    await started.wait()
    manager._remove_group("port")
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
    manager._tasks["port"] = task
    manager._running_tasks.add(task)
    await started.wait()
    manager._remove_group("port")
    await cleaning.wait()
    await manager._shutdown()
    assert cleaned.is_set()
