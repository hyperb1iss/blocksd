"""Execution challenges handled by device-side LED renderers."""

from __future__ import annotations

from blocksd.littlefoot.assembler import BytecodeAssembler, compute_function_id

RENDERER_READY_MARKER = 0x424C4544
BITMAP_RENDERER = 1
KEY_RENDERER = 2


def emit_renderer_query_handler(asm: BytecodeAssembler, renderer_kind: int) -> None:
    """Answer matching host challenges with the supplied nonce.

    Callback arguments sit below the dummy return address on the VM stack.
    Answering from handleMessage also works when identical code is reuploaded
    without another initialise callback.
    """
    asm.begin_function("handleMessage/viii")
    asm.dup_offset(1)
    asm.push32(RENDERER_READY_MARKER)
    asm.sub_int32()
    asm.jump_if_true("ignore_query")
    asm.dup_offset(2)
    asm.push_int(renderer_kind)
    asm.sub_int32()
    asm.jump_if_true("ignore_query")

    asm.dup_offset(3)  # Third callback argument: the host's nonce.
    asm.push_int(renderer_kind)
    asm.push32(RENDERER_READY_MARKER)
    asm.call_native(compute_function_id("sendMessageToHost/viii"))
    asm.label("ignore_query")
    asm.ret_void(3)
