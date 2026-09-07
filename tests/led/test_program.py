"""Renderer challenges prevent stale readiness and startup pixel loss."""

import pytest

from blocksd.led.program import LEDProgram
from blocksd.littlefoot.keys import key_led_program
from blocksd.littlefoot.lifecycle import KEY_RENDERER, RENDERER_READY_MARKER
from blocksd.protocol.remote_heap import RemoteHeap


def finish_upload(heap: RemoteHeap) -> None:
    for _ in range(100):
        heap.send_changes(1)
        if heap.in_flight_count:
            heap.handle_ack((heap.packet_index - 1) & 0x3FF)
        if not heap.is_dirty and heap.in_flight_count == 0:
            return
    pytest.fail("Heap did not synchronize")


def make_program() -> tuple[RemoteHeap, LEDProgram]:
    heap = RemoteHeap(7200)
    return heap, LEDProgram(heap, key_led_program(), KEY_RENDERER, 48)


def pixels_in(heap: RemoteHeap, program: LEDProgram) -> bytes:
    return heap.target[len(program.code) : len(program.code) + 48]


def test_challenge_waits_for_complete_upload_and_ack():
    heap, program = make_program()
    pixels = bytes([31, 0]) * 24
    assert program.set_frame(pixels)
    assert program.advance(0) is None
    while heap.send_changes(1) is not None:
        pass
    assert heap.in_flight_count > 0
    assert program.advance(1) is None
    assert pixels_in(heap, program) == bytes(48)
    finish_upload(heap)
    query = program.advance(2)
    assert query is not None
    assert query[:2] == (RENDERER_READY_MARKER, KEY_RENDERER)
    assert 0 < query[2] <= 0x7FFFFFFF
    assert not program.ready
    assert pixels_in(heap, program) == bytes(48)
    program.on_ready(query)
    assert program.ready
    assert pixels_in(heap, program) == pixels


def test_startup_coalesces_frames_and_rejects_unrelated_events():
    heap, program = make_program()
    assert program.set_frame(bytes([31, 0]) * 24)
    latest = bytes([0, 248]) * 24
    assert program.set_frame(latest)
    assert not program.set_frame(b"invalid")
    finish_upload(heap)
    query = program.advance(0)
    assert query is not None
    for reply in [(0, query[1], query[2]), (query[0], 1, query[2]), (query[0], query[1], 0)]:
        program.on_ready(reply)
        assert not program.ready
    program.on_ready(query)
    assert pixels_in(heap, program) == latest


def test_unanswered_challenge_retries_without_reuploading_code():
    heap, program = make_program()
    finish_upload(heap)
    query = program.advance(0)
    assert query is not None
    assert program.advance(0.1) is None
    assert program.advance(0.25) == query
    assert not heap.is_dirty
    assert heap.in_flight_count == 0
    program.on_ready(query)
    assert program.advance(100) is None


def test_live_frames_and_duplicate_replies_do_not_reload_or_erase_pixels():
    heap, program = make_program()
    finish_upload(heap)
    query = program.advance(0)
    assert query is not None
    program.on_ready(query)
    assert program.set_frame(bytes([255]) * 48)
    finish_upload(heap)
    program.on_ready(query)
    assert pixels_in(heap, program) == bytes([255]) * 48
    assert heap.target[: len(program.code)] == program.code
    assert not heap.is_dirty
    assert program.advance(10) is None


@pytest.mark.parametrize("full_reset", [False, True])
@pytest.mark.parametrize("phase", ["uploading", "querying", "live"])
def test_state_loss_rechallenges_and_preserves_latest_pixels(full_reset, phase):
    heap, program = make_program()
    latest = bytes([31, 0]) * 24
    program.set_frame(latest)
    old_query = None
    if phase != "uploading":
        finish_upload(heap)
        old_query = program.advance(0)
        assert old_query is not None
        if phase == "live":
            program.on_ready(old_query)
            finish_upload(heap)
    else:
        heap.send_changes(1)

    if full_reset:
        heap.reset()
    else:
        heap.reset_device_state()
    assert program.advance(1) is None
    assert not program.ready
    assert pixels_in(heap, program) == bytes(48)
    assert heap.target[: len(program.code)] == program.code
    if old_query:
        program.on_ready(old_query)
        assert not program.ready
    finish_upload(heap)
    new_query = program.advance(2)
    assert new_query is not None
    if old_query:
        assert new_query != old_query
        program.on_ready(old_query)
        assert not program.ready
    program.on_ready(new_query)
    assert program.ready
    assert pixels_in(heap, program) == latest


def test_event_and_frame_entrypoints_detect_reset_before_using_readiness():
    heap, program = make_program()
    finish_upload(heap)
    query = program.advance(0)
    assert query is not None
    program.on_ready(query)
    heap.reset_device_state()
    program.on_ready(query)
    assert not program.ready
    assert pixels_in(heap, program) == bytes(48)
    program.set_frame(bytes([255]) * 48)
    assert pixels_in(heap, program) == bytes(48)


def test_unknown_ack_invalidates_outstanding_challenge():
    heap, program = make_program()
    finish_upload(heap)
    query = program.advance(0)
    assert query is not None
    assert not heap.handle_ack((heap.packet_index + 100) & 0x3FF)
    program.on_ready(query)
    assert not program.ready
    assert program.advance(1) is None
    assert heap.is_dirty
