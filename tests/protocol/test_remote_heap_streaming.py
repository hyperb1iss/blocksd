"""Decode real heap packets while frames arrive faster than a transfer completes."""

from __future__ import annotations

import colorsys
from collections import deque

import pytest

from blocksd.led.bitmap import Color
from blocksd.littlefoot.programs import bitmap_led_program
from blocksd.protocol.constants import BitSize, DataChangeCommand
from blocksd.protocol.packing import Packed7BitReader
from blocksd.protocol.remote_heap import RemoteHeap


def apply_packet(device: bytearray, packet: bytes) -> tuple[int, bool]:
    """Apply the wire command stream independently of RemoteHeap's shadow state."""
    assert len(packet) <= 200
    reader = Packed7BitReader(packet[6:-2])
    reader.read_bits(BitSize.MESSAGE_TYPE)
    index = reader.read_bits(BitSize.PACKET_INDEX)
    cursor = 0
    last_value = None
    while reader.remaining_bits >= BitSize.DATA_CHANGE_COMMAND:
        command = reader.read_bits(BitSize.DATA_CHANGE_COMMAND)
        if command in (DataChangeCommand.END_OF_PACKET, DataChangeCommand.END_OF_CHANGES):
            return index, command == DataChangeCommand.END_OF_CHANGES
        if command in (DataChangeCommand.SKIP_BYTES_FEW, DataChangeCommand.SKIP_BYTES_MANY):
            bits = (
                BitSize.BYTE_COUNT_FEW
                if command == DataChangeCommand.SKIP_BYTES_FEW
                else BitSize.BYTE_COUNT_MANY
            )
            cursor += reader.read_bits(bits)
            continue
        if command == DataChangeCommand.SET_SEQUENCE_OF_BYTES:
            values = bytearray()
            while True:
                last_value = reader.read_bits(BitSize.BYTE_VALUE)
                values.append(last_value)
                if not reader.read_bits(BitSize.BYTE_SEQUENCE_CONTINUES):
                    break
        else:
            bits = (
                BitSize.BYTE_COUNT_MANY
                if command == DataChangeCommand.SET_MANY_BYTES_WITH_VALUE
                else BitSize.BYTE_COUNT_FEW
            )
            count = reader.read_bits(bits)
            if command != DataChangeCommand.SET_FEW_BYTES_WITH_LAST_VALUE:
                last_value = reader.read_bits(BitSize.BYTE_VALUE)
            assert last_value is not None
            values = bytearray([last_value] * count)
        assert cursor + len(values) <= len(device)
        device[cursor : cursor + len(values)] = values
        cursor += len(values)
    raise AssertionError("missing packet end marker")


def drain(heap: RemoteHeap, device: bytearray) -> list[bytes]:
    """Send and acknowledge every remaining packet, retaining completed states."""
    completed = []
    while heap.is_dirty:
        packet = heap.send_changes(1, now=0)
        assert packet is not None
        index, final = apply_packet(device, packet)
        assert heap.handle_ack(index)
        if final:
            completed.append(bytes(device))
    return completed


@pytest.mark.parametrize("ack_ms", [20, 40, 120])
def test_continuous_rainbow_updates_complete_all_rows(ack_ms: int):
    code = bitmap_led_program()
    heap = RemoteHeap(7200)
    device = bytearray([0xA5] * heap.size)
    heap.set_bytes(0, code)
    drain(heap, device)
    assert device == code + bytes(heap.size - len(code))
    pending: deque[bytes] = deque()
    frames: set[bytes] = set()
    row_updates = [0] * 15
    completed = 0

    def flush(now: float) -> None:
        while (packet := heap.send_changes(1, now)) is not None:
            pending.append(packet)

    def acknowledge(now: float) -> None:
        nonlocal completed
        before = device[:]
        index, final = apply_packet(device, pending.popleft())
        assert heap.handle_ack(index)
        for row in range(15):
            start = len(code) + row * 30
            if device[start : start + 30] != before[start : start + 30]:
                row_updates[row] += 1
        if final:
            assert bytes(device[len(code) : len(code) + 450]) in frames
            completed += 1
        flush(now)

    for ms in range(0, 15000, 20):
        if ms % 40 == 0:
            row = bytearray()
            for x in range(15):
                rgb = colorsys.hsv_to_rgb((x / 15 + ms / 6000) % 1, 1, 0.75)
                row.extend(Color(*(round(value * 255) for value in rgb)).to_rgb565())
            pixels = bytes(row * 15)
            frames.add(pixels)
            heap.set_bytes(len(code), pixels)
            flush(ms / 1000)
        if ms % ack_ms == 0 and pending:
            acknowledge(ms / 1000)

    # Every row progresses during the stream, before the final drain.
    assert min(row_updates) >= 10, row_updates
    assert completed >= 10
    for _ in range(100):
        if not pending:
            break
        acknowledge(15)
    assert not pending
    assert not heap.is_dirty
    assert device == heap.target


def test_reverting_target_finishes_snapshot_then_restores_latest():
    baseline = bytes(i % 251 + 1 for i in range(600))
    changed = bytes(value ^ 0x5A for value in baseline)
    heap = RemoteHeap(len(baseline))
    device = bytearray(len(baseline))
    heap.set_bytes(0, baseline)
    drain(heap, device)
    heap.set_bytes(0, changed)
    first = heap.send_changes(1, now=0)
    assert first is not None
    index, final = apply_packet(device, first)
    assert not final
    assert heap.handle_ack(index)
    heap.set_bytes(0, baseline)
    completed = drain(heap, device)
    assert completed == [changed, baseline]
    assert device == baseline


@pytest.mark.parametrize("reset", ["reset", "reset_device_state", "unknown_ack"])
def test_reset_discards_partial_snapshot(reset: str):
    heap = RemoteHeap(600)
    old = bytes(i % 251 + 1 for i in range(heap.size))
    newest = bytes(value ^ 0xFF for value in old)
    heap.set_bytes(0, old)
    assert heap.send_changes(1, now=0) is not None
    if reset == "unknown_ack":
        assert not heap.handle_ack(99)
    else:
        getattr(heap, reset)()
    heap.set_bytes(0, newest)
    device = bytearray([0xA5] * heap.size)
    assert drain(heap, device) == [newest]
    assert device == newest
