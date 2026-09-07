"""Bitmap bank ownership survives asynchronous upload and presentation replies."""

from __future__ import annotations

import pytest

from blocksd.led.buffered_program import BufferedLEDProgram
from blocksd.littlefoot.bitmap_lifecycle import NOT_READY, PRESENT_BASE, PRESENTED_BASE
from blocksd.littlefoot.lifecycle import BITMAP_RENDERER
from blocksd.littlefoot.programs import bitmap_led_program
from blocksd.protocol.remote_heap import RemoteHeap
from tests.led.test_program import finish_upload


def make_program() -> tuple[RemoteHeap, BufferedLEDProgram]:
    heap = RemoteHeap(7200)
    return heap, BufferedLEDProgram(heap, bitmap_led_program(), BITMAP_RENDERER, 450)


def bank(heap: RemoteHeap, program: BufferedLEDProgram, index: int) -> bytes:
    start = len(program.code) + 450 * index
    return heap.target[start : start + 450]


def acknowledge_present(program: BufferedLEDProgram, request: tuple[int, int, int]) -> None:
    program.on_ready((PRESENTED_BASE | (request[0] & 1), request[1], request[2]))


def ready(heap: RemoteHeap, program: BufferedLEDProgram) -> tuple[int, int, int]:
    finish_upload(heap)
    request = program.advance(0)
    assert request is not None
    program.on_ready(request)
    assert program.ready
    return request


def test_first_frame_waits_for_ready_and_complete_bank_ack():
    heap, program = make_program()
    pixels = bytes(range(225)) * 2
    program.set_frame(pixels)
    assert program.advance(0) is None
    assert bank(heap, program, 0) == bank(heap, program, 1) == bytes(450)
    query = ready(heap, program)
    assert bank(heap, program, 0) == bytes(450)
    assert bank(heap, program, 1) == pixels
    assert program.advance(1) is None
    while heap.send_changes(1) is not None:
        pass
    assert heap.in_flight_count
    assert program.advance(2) is None
    finish_upload(heap)
    request = program.advance(3)
    assert request == (PRESENT_BASE | 1, query[2], 1)
    acknowledge_present(program, request)
    assert program.advance(4) is None


def test_pending_frame_is_immutable_and_latest_frame_uses_released_bank():
    heap, program = make_program()
    first, second, latest = (bytes([value]) * 450 for value in (1, 2, 3))
    program.set_frame(first)
    ready(heap, program)
    program.set_frame(second)
    program.set_frame(latest)
    assert bank(heap, program, 0) == bytes(450)
    assert bank(heap, program, 1) == first
    finish_upload(heap)
    request = program.advance(1)
    assert request is not None
    program.set_frame(second)
    program.set_frame(latest)
    assert bank(heap, program, 0) == bytes(450)
    assert bank(heap, program, 1) == first
    acknowledge_present(program, request)
    assert bank(heap, program, 1) == first
    assert bank(heap, program, 0) == latest
    finish_upload(heap)
    next_request = program.advance(2)
    assert next_request == (PRESENT_BASE, request[1], 2)
    acknowledge_present(program, next_request)
    assert program.advance(3) is None


def test_lost_presentation_reply_retries_without_rewriting_either_bank():
    heap, program = make_program()
    program.set_frame(bytes([7]) * 450)
    ready(heap, program)
    finish_upload(heap)
    request = program.advance(1)
    assert request is not None
    target = heap.target
    program.set_frame(bytes([8]) * 450)
    assert program.advance(1.1) is None
    assert program.advance(1.25) == request
    assert heap.target == target
    assert not heap.is_dirty
    acknowledge_present(program, request)
    assert bank(heap, program, 0) == bytes([8]) * 450


def test_unsolicited_wrong_bank_epoch_and_sequence_replies_do_not_release_bank():
    heap, program = make_program()
    program.set_frame(bytes([1]) * 450)
    query = ready(heap, program)
    # Even the right tuple is inert before PRESENT was sent.
    early = (PRESENTED_BASE | 1, query[2], 1)
    program.on_ready(early)
    program.set_frame(bytes([2]) * 450)
    assert bank(heap, program, 0) == bytes(450)
    finish_upload(heap)
    request = program.advance(1)
    assert request is not None
    for response in [
        (PRESENTED_BASE, request[1], request[2]),
        (PRESENTED_BASE | 1, request[1] + 1, request[2]),
        (PRESENTED_BASE | 1, request[1], request[2] + 1),
        query,
        (NOT_READY, request[1] + 1, request[2]),
        (NOT_READY, request[1], request[2] + 1),
    ]:
        program.on_ready(response)
        assert bank(heap, program, 0) == bytes(450)
        assert program.ready
    acknowledge_present(program, request)
    assert bank(heap, program, 0) == bytes([2]) * 450
    target = heap.target
    acknowledge_present(program, request)
    assert heap.target == target


@pytest.mark.parametrize("reset", ["reset", "reset_device_state", "unknown_ack", "vm_restart"])
@pytest.mark.parametrize("presented", [False, True])
def test_reset_renegotiates_session_before_uploading_latest_frame(reset: str, presented: bool):
    heap, program = make_program()
    first, latest = bytes([1]) * 450, bytes([2]) * 450
    program.set_frame(first)
    old_query = ready(heap, program)
    finish_upload(heap)
    old_request = program.advance(1)
    assert old_request is not None
    if presented:
        acknowledge_present(program, old_request)
        program.set_frame(latest)
        finish_upload(heap)
        old_request = program.advance(1.5)
        assert old_request is not None and old_request[0] == PRESENT_BASE
    program.set_frame(latest)
    if reset == "vm_restart":
        program.on_ready((NOT_READY, old_request[1], old_request[2]))
    elif reset == "unknown_ack":
        assert not heap.handle_ack((heap.packet_index + 99) & 0x3FF)
    else:
        getattr(heap, reset)()
    assert program.advance(2) is None
    assert not program.ready
    assert bank(heap, program, 0) == bank(heap, program, 1) == bytes(450)
    acknowledge_present(program, old_request)
    program.on_ready(old_query)
    assert not program.ready
    finish_upload(heap)
    query = program.advance(3)
    assert query is not None and query[2] != old_query[2]
    program.on_ready(query)
    assert program.ready
    assert bank(heap, program, 0) == bytes(450)
    assert bank(heap, program, 1) == latest
    finish_upload(heap)
    request = program.advance(4)
    assert request == (PRESENT_BASE | 1, query[2], 1)
    acknowledge_present(program, old_request)
    assert program.advance(4.25) == request
    acknowledge_present(program, request)
    assert program.advance(5) is None


def test_invalid_frame_and_unchanged_visible_frame_do_not_start_transfers():
    heap, program = make_program()
    ready(heap, program)
    assert not program.set_frame(b"bad")
    assert program.set_frame(bytes(450))
    assert program.advance(1) is None
    assert not heap.is_dirty
