"""MIDI reception runs independently of the device lifecycle timer."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from blocksd.topology import device_group
from blocksd.topology.device_group import TICK_INTERVAL, DeviceGroup, GroupState
from tests.topology.test_device_group import _build_ack_packet


class QueueTransport:
    name = "Queued MIDI"

    def __init__(self):
        self.queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.is_open = True
        self.close_calls = 0

    def send(self, data):
        return self.is_open

    def drain(self):
        messages = []
        while not self.queue.empty():
            if (message := self.queue.get_nowait()) is not None:
                messages.append(message)
        return messages

    async def recv(self, timeout=None):
        try:
            return await asyncio.wait_for(self.queue.get(), timeout)
        except TimeoutError:
            return None

    def close(self):
        self.close_calls += 1
        self.is_open = False


class RecordingGroup(DeviceGroup):
    def __init__(self, transport):
        super().__init__(transport)
        self.ticks = []
        self.first_tick = asyncio.Event()
        self.received = asyncio.Event()
        self.acks = []
        self.remove_calls = 0

    def _lifecycle_timer(self, now):
        self.ticks.append(now)
        self.first_tick.set()

    def on_packet_ack(self, device_index, counter):
        self.acks.append((device_index, counter))
        self.received.set()

    def _remove_all_devices(self):
        self.remove_calls += 1


@pytest.mark.asyncio
async def test_ack_arriving_between_lifecycle_ticks_is_processed_immediately(monkeypatch):
    # Widen the old sleeping window without tightening CI scheduling demands.
    interval = 2.0
    monkeypatch.setattr(device_group, "TICK_INTERVAL", interval)
    transport = QueueTransport()
    group = RecordingGroup(transport)
    task = asyncio.create_task(group.run())
    try:
        await group.first_tick.wait()
        await asyncio.sleep(0.02)
        transport.queue.put_nowait(_build_ack_packet(0, counter=123))
        await asyncio.wait_for(group.received.wait(), interval / 2)
        assert group.acks == [(0, 123)]
        assert len(group.ticks) == 1
    finally:
        task.cancel()
        await task
    assert transport.close_calls == group.remove_calls == 1


@pytest.mark.asyncio
async def test_preloaded_receive_burst_preserves_timer_cadence_and_peer_progress(monkeypatch):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(device_group, "time", SimpleNamespace(monotonic=lambda: clock.now))
    packet = _build_ack_packet(0, counter=1)

    class BurstTransport(QueueTransport):
        async def recv(self, timeout=None):
            # No suspension: model a transport with a preloaded receive queue.
            clock.now += 0.003
            if clock.now >= 0.7:
                self.is_open = False
                return None
            return packet

    transport = BurstTransport()
    group = RecordingGroup(transport)
    peer_turns = 0

    async def peer():
        nonlocal peer_turns
        while transport.is_open:
            peer_turns += 1
            await asyncio.sleep(0)

    await asyncio.gather(group.run(), peer())
    assert len(group.acks) > 200
    assert peer_turns > 200
    assert len(group.ticks) == 4
    for index, actual in enumerate(group.ticks):
        assert abs(actual - index * TICK_INTERVAL) < 0.0031
    assert transport.close_calls == group.remove_calls == 1


@pytest.mark.asyncio
async def test_idle_receive_waits_until_lifecycle_deadline(monkeypatch):
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(device_group, "time", SimpleNamespace(monotonic=lambda: clock.now))
    deadlines = []

    class IdleTransport(QueueTransport):
        async def recv(self, timeout=None):
            assert timeout is not None and timeout > 0
            deadlines.append(timeout)
            clock.now += timeout
            if len(deadlines) == 3:
                self.is_open = False

    transport = IdleTransport()
    group = RecordingGroup(transport)
    await group.run()
    assert deadlines == pytest.approx([TICK_INTERVAL] * 3)
    assert group.ticks == pytest.approx([0, TICK_INTERVAL, TICK_INTERVAL * 2])
    assert transport.close_calls == group.remove_calls == 1


@pytest.mark.asyncio
async def test_closing_transport_ends_receive_loop_and_cleans_up():
    transport = QueueTransport()
    group = RecordingGroup(transport)
    task = asyncio.create_task(group.run())
    await group.first_tick.wait()
    transport.is_open = False
    transport.queue.put_nowait(None)
    await asyncio.wait_for(task, 1)
    assert transport.close_calls == group.remove_calls == 1


@pytest.mark.asyncio
async def test_receive_error_still_removes_devices_and_closes_transport():
    class BrokenTransport(QueueTransport):
        async def recv(self, timeout=None):
            raise OSError("transport failed")

    transport = BrokenTransport()
    group = RecordingGroup(transport)
    with pytest.raises(OSError, match="transport failed"):
        await group.run()
    assert transport.close_calls == group.remove_calls == 1


@pytest.mark.asyncio
async def test_failed_lifecycle_does_not_start_another_receive():
    class FailedGroup(RecordingGroup):
        def _lifecycle_timer(self, now):
            super()._lifecycle_timer(now)
            self.state = GroupState.FAILED

    class NoReceiveTransport(QueueTransport):
        async def recv(self, timeout=None):
            raise AssertionError("failed lifecycle must not receive again")

    transport = NoReceiveTransport()
    group = FailedGroup(transport)
    await group.run()
    assert transport.close_calls == group.remove_calls == 1
