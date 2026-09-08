"""LUMI key lighting with the firmware's musical key handling preserved."""

from __future__ import annotations

from functools import lru_cache

from blocksd.littlefoot.assembler import BytecodeAssembler, compute_function_id
from blocksd.littlefoot.lifecycle import KEY_RENDERER, emit_renderer_query_handler

KEY_COUNT = 24
KEY_HEAP_SIZE = KEY_COUNT * 2

# ROLI BlockConfigId::brightness, with BlockConfigManager's 0..100 range.
_HARDWARE_BRIGHTNESS = 36
_MAX_HARDWARE_BRIGHTNESS = 100


def _emit_hardware_brightness(asm: BytecodeAssembler) -> None:
    """Keep brightness scaling in the host RGB pipeline."""
    asm.push_int(_MAX_HARDWARE_BRIGHTNESS)
    asm.push_int(_HARDWARE_BRIGHTNESS)
    asm.call_native(compute_function_id("setLocalConfig/vii"))


@lru_cache(maxsize=1)
def key_led_program() -> bytes:
    """Build a 24-key RGB565 renderer for LUMI firmware 1.3.0 or newer.

    The 48-byte heap uses the same little-endian RGB565 layout as LEDGrid,
    in key-index order. Initialise keeps the default touch/MIDI handler and
    replaces only key lighting. Repaint calls fillPixel(colour, key, 0).
    """
    asm = BytecodeAssembler(heap_size=KEY_HEAP_SIZE)
    asm.begin_function("initialise/v")
    _emit_hardware_brightness(asm)
    asm.push0()
    asm.call_native(compute_function_id("setStatusOverlayActive/vb"))
    # Native arguments are pushed right to left: lighting=false, touch=true.
    asm.push0()
    asm.push1()
    asm.call_native(compute_function_id("setUseDefaultKeyHandler/vbb"))
    asm.ret_void()

    asm.begin_function("repaint/v")
    asm.push0()
    asm.label("key")
    asm.dup()
    asm.push8(KEY_COUNT)
    asm.sub_int32()
    asm.test_lt_int32()
    asm.jump_if_false("done")

    asm.dup()
    asm.push8(16)
    asm.mul_int32()
    # Stack: key, bit offset. Supply y=0 and x=key before the colour.
    asm.push0()
    asm.dup_offset(2)

    # Each colour read supplies numBits before startBit (the VM's TOS).
    for bit_offset, bit_count, shift, stack_offset in ((11, 5, 3, 3), (5, 6, 2, 4), (0, 5, 3, 5)):
        asm.push8(bit_count)
        asm.dup_offset(stack_offset)
        if bit_offset:
            asm.push8(bit_offset)
            asm.add_int32()
        asm.get_heap_bits()
        asm.push8(shift)
        asm.bit_shift_left()

    asm.push16(255)
    asm.call_native(compute_function_id("makeARGB/iiiii"))
    asm.call_native(compute_function_id("fillPixel/viii"))
    asm.drop()  # Discard bit offset; retain the key counter.
    asm.push1()
    asm.add_int32()
    asm.jump("key")

    asm.label("done")
    asm.drop()
    asm.ret_void()
    emit_renderer_query_handler(asm, KEY_RENDERER, on_ready=_emit_hardware_brightness)
    return asm.build()


def key_led_program_size() -> int:
    """Return the byte offset where the renderer's 48-byte pixel heap begins."""
    return len(key_led_program())
