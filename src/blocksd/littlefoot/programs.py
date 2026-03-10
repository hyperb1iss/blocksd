"""Pre-assembled LittleFoot programs for ROLI Blocks devices.

BitmapLEDProgram: reads RGB565 pixel data from the device heap and
paints the 15x15 LED grid. This is the program that enables host-side
LED control — the host writes pixel data to the heap via SharedDataChange,
and this program renders it on every repaint cycle (~25 Hz).
"""

from __future__ import annotations

from functools import lru_cache

from blocksd.littlefoot.assembler import BytecodeAssembler, compute_function_id

# Native function IDs (computed from signatures)
_MAKE_ARGB = compute_function_id("makeARGB/iiiii")
_FILL_PIXEL = compute_function_id("fillPixel/viii")

# Grid dimensions
_COLS = 15
_ROWS = 15
_BITS_PER_PIXEL = 16
_HEAP_SIZE = _COLS * _ROWS * 2  # 450 bytes (RGB565)


@lru_cache(maxsize=1)
def bitmap_led_program() -> bytes:
    """Assemble the BitmapLEDProgram bytecode.

    Equivalent LittleFoot source:
        #heapsize: 450

        void repaint() {
            for (int y = 0; y < 15; ++y)
                for (int x = 0; x < 15; ++x) {
                    int bit = (x + y * 15) * 16;
                    fillPixel(makeARGB(255,
                        getHeapBits(bit, 5) << 3,
                        getHeapBits(bit + 5, 6) << 2,
                        getHeapBits(bit + 11, 5) << 3),
                        x, y);
                }
        }

    Calling conventions (from roli_LittleFootCompiler.h):
    - Arguments are pushed RIGHT-TO-LEFT (last arg first, first arg last = TOS)
    - callNative: stack[0] = first arg after flush
    - Built-in opcodes (getHeapBits): TOS = first arg, *stack++ = second arg
    """
    asm = BytecodeAssembler(heap_size=_HEAP_SIZE)
    asm.begin_function("repaint/v")

    # --- Outer loop: for (y = 0; y < 15; y++) ---
    asm.push0()  # y = 0                          stack: [y]

    asm.label("y_top")
    asm.dup()  # dup y                             stack: [y, y]
    asm.push8(_ROWS)  # push 15                    stack: [y, y, 15]
    asm.sub_int32()  # y - 15                      stack: [y, y-15]
    asm.test_lt_int32()  # (y-15) < 0 → y < 15    stack: [y, cond]
    asm.jump_if_false("y_end")  #                  stack: [y]

    # --- Inner loop: for (x = 0; x < 15; x++) ---
    asm.push0()  # x = 0                           stack: [y, x]

    asm.label("x_top")
    asm.dup()  # dup x                             stack: [y, x, x]
    asm.push8(_COLS)  # push 15                    stack: [y, x, x, 15]
    asm.sub_int32()  # x - 15                      stack: [y, x, x-15]
    asm.test_lt_int32()  # x < 15                  stack: [y, x, cond]
    asm.jump_if_false("x_end")  #                  stack: [y, x]

    # --- Compute bit = (x + y * 15) * 16 ---
    asm.dup()  # dup x                             stack: [y, x, x]
    asm.dup_offset(2)  # get y                     stack: [y, x, x, y]
    asm.push8(_COLS)  #                            stack: [y, x, x, y, 15]
    asm.mul_int32()  # y * 15                      stack: [y, x, x, y*15]
    asm.add_int32()  # x + y*15                    stack: [y, x, x+y*15]
    asm.push8(_BITS_PER_PIXEL)  #                  stack: [y, x, x+y*15, 16]
    asm.mul_int32()  # bit                         stack: [y, x, bit]

    # --- fillPixel(makeARGB(255, r, g, b), x, y) ---
    # Push args RTL: y (3rd), x (2nd), then makeARGB result (1st)

    asm.dup_offset(2)  # push y (fillPixel 3rd)    stack: [y, x, bit, y']
    asm.dup_offset(2)  # push x (fillPixel 2nd)    stack: [y, x, bit, y', x']

    # --- makeARGB(255, r, g, b) — push RTL: b, g, r, 255 ---

    # Blue = getHeapBits(bit+11, 5) << 3
    # getHeapBits: push numBits first, push startBit last (TOS)
    asm.push8(5)  # numBits                        stack: [.., x', 5]
    asm.dup_offset(3)  # bit                       stack: [.., x', 5, bit]
    asm.push8(11)  #                               stack: [.., x', 5, bit, 11]
    asm.add_int32()  # bit + 11                    stack: [.., x', 5, bit+11]
    asm.get_heap_bits()  # blue5                   stack: [.., x', blue5]
    asm.push8(3)  #                                stack: [.., x', blue5, 3]
    asm.bit_shift_left()  # blue                   stack: [.., x', blue]

    # Green = getHeapBits(bit+5, 6) << 2
    asm.push8(6)  # numBits                        stack: [.., blue, 6]
    asm.dup_offset(4)  # bit                       stack: [.., blue, 6, bit]
    asm.push8(5)  #                                stack: [.., blue, 6, bit, 5]
    asm.add_int32()  # bit + 5                     stack: [.., blue, 6, bit+5]
    asm.get_heap_bits()  # green6                  stack: [.., blue, green6]
    asm.push8(2)  #                                stack: [.., blue, green6, 2]
    asm.bit_shift_left()  # green                  stack: [.., blue, green]

    # Red = getHeapBits(bit, 5) << 3
    asm.push8(5)  # numBits                        stack: [.., green, 5]
    asm.dup_offset(5)  # bit                       stack: [.., green, 5, bit]
    asm.get_heap_bits()  # red5                    stack: [.., green, red5]
    asm.push8(3)  #                                stack: [.., green, red5, 3]
    asm.bit_shift_left()  # red                    stack: [.., green, red]

    # Alpha = 255 (push8 range is -128..127, so use push16)
    asm.push16(255)  # alpha                       stack: [.., red, 255]

    # callNative makeARGB(alpha=255, r, g, b) → returns argb
    # After flush+call: stack[0]=255, stack[1]=red, stack[2]=green, stack[3]=blue
    asm.call_native(_MAKE_ARGB)  #                 stack: [y, x, bit, y', x', argb]

    # callNative fillPixel(argb, x, y) → void
    # After flush: stack[0]=argb, stack[1]=x', stack[2]=y'
    # Void return auto-drops → pops 'bit' into TOS
    asm.call_native(_FILL_PIXEL)  #                stack: [y, x, bit]

    # Drop bit
    asm.drop()  #                                  stack: [y, x]

    # --- Increment x ---
    asm.push1()  #                                 stack: [y, x, 1]
    asm.add_int32()  # x + 1                       stack: [y, x+1]
    asm.jump("x_top")

    asm.label("x_end")
    asm.drop()  # discard x                        stack: [y]

    # --- Increment y ---
    asm.push1()  #                                 stack: [y, 1]
    asm.add_int32()  # y + 1                       stack: [y+1]
    asm.jump("y_top")

    asm.label("y_end")
    asm.drop()  # discard y                        stack: []
    asm.ret_void(0)

    return asm.build()


def bitmap_led_program_size() -> int:
    """Return the size of the compiled BitmapLEDProgram in bytes."""
    return len(bitmap_led_program())
