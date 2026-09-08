"""Bank ownership and presentation messages for the bitmap renderer."""

from __future__ import annotations

from blocksd.littlefoot.assembler import BytecodeAssembler, compute_function_id
from blocksd.littlefoot.lifecycle import BITMAP_RENDERER, RENDERER_READY_MARKER

BITMAP_FRAME_BYTES = 450
PRESENT_BASE = 0x424C5000
PRESENTED_BASE = 0x424C4100
NOT_READY = 0x424C4E52
BITMAP_GLOBALS = 6

_SESSION = 0
_ACTIVE_BANK = 1
_PENDING_BANK = 2
_PENDING_SEQUENCE = 3
_PRESENTED_SEQUENCE = 4
_READY_PENDING = 5
_SEND_MESSAGE = compute_function_id("sendMessageToHost/viii")


def emit_bitmap_repaint_begin(asm: BytecodeAssembler) -> None:
    """Latch session, readiness, bank, and presentation identity for this draw."""
    asm.dup_from_global(_SESSION)
    asm.dup_from_global(_READY_PENDING)
    asm.push0()
    asm.drop_to_global(_READY_PENDING)
    asm.dup_from_global(_PENDING_SEQUENCE)
    asm.jump_if_false("no_pending_bank")
    asm.dup_from_global(_PENDING_BANK)
    asm.drop_to_global(_ACTIVE_BANK)
    asm.dup_from_global(_PENDING_SEQUENCE)
    asm.drop_to_global(_PRESENTED_SEQUENCE)
    asm.label("no_pending_bank")
    asm.dup_from_global(_ACTIVE_BANK)
    asm.dup_from_global(_PENDING_SEQUENCE)
    asm.push0()
    asm.drop_to_global(_PENDING_SEQUENCE)
    # Stack: session, readiness, bank, sequence, bit base.
    asm.dup_offset(1)
    asm.push16(BITMAP_FRAME_BYTES * 8)
    asm.mul_int32()


def emit_bitmap_repaint_end(asm: BytecodeAssembler) -> None:
    """Acknowledge only after the complete draw, using its latched identity."""
    asm.drop()  # Bit base.
    asm.dup_offset(3)
    asm.dup_from_global(_SESSION)
    asm.sub_int32()
    asm.jump_if_true("draw_ack_done")
    asm.dup_offset(2)
    asm.jump_if_false("draw_present_ack")
    asm.dup_offset(3)
    asm.push_int(BITMAP_RENDERER)
    asm.push32(RENDERER_READY_MARKER)
    asm.call_native(_SEND_MESSAGE)
    asm.label("draw_present_ack")
    asm.dup()
    asm.jump_if_false("draw_ack_done")
    asm.dup()
    asm.dup_offset(4)
    asm.dup_offset(3)
    asm.push32(PRESENTED_BASE)
    asm.add_int32()
    asm.call_native(_SEND_MESSAGE)
    asm.label("draw_ack_done")
    for _ in range(4):
        asm.drop()


def emit_bitmap_message_handler(asm: BytecodeAssembler) -> None:
    """Process ordered session changes and idempotent bank presentations.

    READY establishes a new session on the ordered MIDI stream. Retrying the
    current session never resets bank ownership. PRESENT identifies its session,
    sequence, and bank independently, so delayed presentation retries are inert.
    """
    asm.begin_function("handleMessage/viii")
    asm.dup_offset(1)
    asm.push32(RENDERER_READY_MARKER)
    asm.sub_int32()
    asm.jump_if_true("check_present_markers")
    asm.dup_offset(2)
    asm.push_int(BITMAP_RENDERER)
    asm.sub_int32()
    asm.jump_if_true("ignore_bitmap_message")
    asm.dup_offset(3)
    asm.push1()
    asm.sub_int32()
    asm.test_ge_int32()
    asm.jump_if_false("ignore_bitmap_message")
    asm.dup_offset(3)
    asm.dup_from_global(_SESSION)
    asm.sub_int32()
    asm.jump_if_false("ready_session_set")
    asm.dup_offset(3)
    asm.drop_to_global(_SESSION)
    for index in (_ACTIVE_BANK, _PENDING_BANK, _PENDING_SEQUENCE, _PRESENTED_SEQUENCE):
        asm.push0()
        asm.drop_to_global(index)
    asm.label("ready_session_set")
    asm.push1()
    asm.drop_to_global(_READY_PENDING)
    asm.ret_void(3)

    asm.label("check_present_markers")
    for bank in (0, 1):
        asm.dup_offset(1)
        asm.push32(PRESENT_BASE | bank)
        asm.sub_int32()
        asm.jump_if_false(f"present_bank_{bank}")
    asm.jump("ignore_bitmap_message")
    for bank in (0, 1):
        _emit_present_bank(asm, bank)
    asm.label("wrong_session")
    asm.dup_offset(3)
    asm.dup_offset(3)
    asm.push32(NOT_READY)
    asm.call_native(_SEND_MESSAGE)
    asm.label("ignore_bitmap_message")
    asm.ret_void(3)


def _emit_present_bank(asm: BytecodeAssembler, bank: int) -> None:
    asm.label(f"present_bank_{bank}")
    asm.dup_offset(2)
    asm.dup_from_global(_SESSION)
    asm.sub_int32()
    asm.jump_if_true("wrong_session")
    asm.dup_offset(3)
    asm.push1()
    asm.sub_int32()
    asm.test_ge_int32()
    asm.jump_if_false("ignore_bitmap_message")
    asm.dup_offset(3)
    asm.dup_from_global(_PRESENTED_SEQUENCE)
    asm.sub_int32()
    asm.jump_if_false(f"repeat_bank_{bank}")
    asm.dup_offset(3)
    asm.dup_from_global(_PRESENTED_SEQUENCE)
    asm.sub_int32()
    asm.push1()
    asm.sub_int32()
    asm.jump_if_true("ignore_bitmap_message")
    # A new sequence may only select the inactive bank.
    asm.dup_from_global(_ACTIVE_BANK)
    asm.push_int(bank)
    asm.sub_int32()
    asm.jump_if_false("ignore_bitmap_message")
    asm.jump(f"queue_bank_{bank}")
    asm.label(f"repeat_bank_{bank}")
    asm.dup_from_global(_ACTIVE_BANK)
    asm.push_int(bank)
    asm.sub_int32()
    asm.jump_if_true("ignore_bitmap_message")
    asm.label(f"queue_bank_{bank}")
    asm.dup_from_global(_PENDING_SEQUENCE)
    asm.jump_if_false(f"store_bank_{bank}")
    asm.dup_from_global(_PENDING_SEQUENCE)
    asm.dup_offset(4)
    asm.sub_int32()
    asm.jump_if_true("ignore_bitmap_message")
    asm.label(f"store_bank_{bank}")
    asm.push_int(bank)
    asm.drop_to_global(_PENDING_BANK)
    asm.dup_offset(3)
    asm.drop_to_global(_PENDING_SEQUENCE)
    asm.ret_void(3)
