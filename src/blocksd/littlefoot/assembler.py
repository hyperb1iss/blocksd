"""LittleFoot bytecode assembler — emit opcodes, resolve labels, build programs.

Produces binary bytecode matching the format expected by the LittleFoot VM
in ROLI Blocks devices (roli_LittleFootRunner.h).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from blocksd.littlefoot.opcodes import Op

# Program header: checksum(2) + program_size(2) + num_functions(2) + num_globals(2) + heap_size(2)
_HEADER_SIZE = 10
# Function table entry: function_id(2) + code_offset(2)
_FUNC_ENTRY_SIZE = 4


def compute_function_id(signature: str) -> int:
    """Compute a FunctionID from a LittleFoot function signature.

    Signature format: "name/return_type param_types"
    e.g. "fillPixel/viii", "makeARGB/iiiii", "repaint/v"

    The return type character (immediately after '/') is excluded from the hash.
    Returns a signed 16-bit integer (matching ROLI's int16 FunctionID).
    """
    slash_pos = signature.index("/")

    h: int = 0
    for i, ch in enumerate(signature):
        if i != slash_pos + 1:  # skip return type char
            h = (h * 31 + ord(ch)) & 0xFFFFFFFF

    result = (h + len(signature)) & 0xFFFF
    # Convert to signed int16
    if result >= 0x8000:
        result -= 0x10000
    return result


def compute_program_checksum(program_bytes: bytearray) -> int:
    """Calculate the LittleFoot program checksum (uint16).

    Matches roli_LittleFootRunner.h Program::calculateChecksum():
    n = program_size; for each byte from index 2 onward: n = (n + n*2 + byte) & 0xFFFF
    """
    n = len(program_bytes) & 0xFFFF
    for byte in program_bytes[2:]:
        n = (n + (n * 2) + byte) & 0xFFFF
    return n


@dataclass
class _LabelFixup:
    """A forward reference to a label that needs patching."""

    code_offset: int  # position in code where the int16 address lives
    label: str


@dataclass
class _FunctionEntry:
    """A function in the program's function table."""

    function_id: int
    code_offset: int = 0


class BytecodeAssembler:
    """Assembles LittleFoot bytecode with label support and program packaging.

    Usage:
        asm = BytecodeAssembler(heap_size=450)
        asm.begin_function("repaint/v")
        asm.push0()
        asm.label("loop")
        # ... emit opcodes ...
        asm.jump("loop")
        asm.ret_void(0)
        program = asm.build()
    """

    def __init__(self, heap_size: int = 0, num_globals: int = 0) -> None:
        self._code = bytearray()
        self._functions: list[_FunctionEntry] = []
        self._labels: dict[str, int] = {}
        self._fixups: list[_LabelFixup] = []
        self._heap_size = heap_size
        self._num_globals = num_globals

    # ── Function management ──────────────────────────────────────────────

    def begin_function(self, signature: str) -> None:
        """Start a new function. The signature determines its FunctionID."""
        func_id = compute_function_id(signature)
        self._functions.append(_FunctionEntry(function_id=func_id, code_offset=len(self._code)))

    # ── Labels and jumps ─────────────────────────────────────────────────

    def label(self, name: str) -> None:
        """Define a label at the current code position."""
        self._labels[name] = len(self._code)

    def _emit_jump(self, op: Op, target: str) -> None:
        """Emit a jump instruction with a label reference."""
        self._emit_byte(op)
        self._fixups.append(_LabelFixup(code_offset=len(self._code), label=target))
        self._emit_byte(0)  # placeholder int16 LE
        self._emit_byte(0)

    # ── Opcodes ──────────────────────────────────────────────────────────

    def halt(self) -> None:
        self._emit_byte(Op.HALT)

    def jump(self, label: str) -> None:
        self._emit_jump(Op.JUMP, label)

    def jump_if_true(self, label: str) -> None:
        self._emit_jump(Op.JUMP_IF_TRUE, label)

    def jump_if_false(self, label: str) -> None:
        self._emit_jump(Op.JUMP_IF_FALSE, label)

    def call(self, label: str) -> None:
        self._emit_jump(Op.CALL, label)

    def ret_void(self, num_args: int = 0) -> None:
        self._emit_byte(Op.RET_VOID)
        self._emit_byte(num_args & 0xFF)

    def ret_value(self, num_args: int = 0) -> None:
        self._emit_byte(Op.RET_VALUE)
        self._emit_byte(num_args & 0xFF)

    def call_native(self, function_id: int) -> None:
        self._emit_byte(Op.CALL_NATIVE)
        self._emit_i16(function_id)

    def call_native_by_sig(self, signature: str) -> None:
        self.call_native(compute_function_id(signature))

    def drop(self) -> None:
        self._emit_byte(Op.DROP)

    def drop_multiple(self, count: int) -> None:
        self._emit_byte(Op.DROP_MULTIPLE)
        self._emit_byte(count & 0xFF)

    def push_multiple_0(self, count: int) -> None:
        self._emit_byte(Op.PUSH_MULTIPLE_0)
        self._emit_byte(count & 0xFF)

    def push0(self) -> None:
        self._emit_byte(Op.PUSH_0)

    def push1(self) -> None:
        self._emit_byte(Op.PUSH_1)

    def push8(self, value: int) -> None:
        self._emit_byte(Op.PUSH_8)
        self._emit_byte(value & 0xFF)

    def push16(self, value: int) -> None:
        self._emit_byte(Op.PUSH_16)
        self._emit_i16(value)

    def push32(self, value: int) -> None:
        self._emit_byte(Op.PUSH_32)
        self._emit_i32(value)

    def push_int(self, value: int) -> None:
        """Push an integer using the most compact encoding."""
        if value == 0:
            self.push0()
        elif value == 1:
            self.push1()
        elif -128 <= value <= 127:
            self.push8(value)
        elif -32768 <= value <= 32767:
            self.push16(value)
        else:
            self.push32(value)

    def dup(self) -> None:
        self._emit_byte(Op.DUP)

    def dup_offset(self, offset: int) -> None:
        # Always use the general form with explicit int8 operand.
        # Firmware v1.1.0 doesn't have the fast-path dupOffset_01-07
        # opcodes — position 0x12 is the general dupOffset(int8).
        if offset <= 0xFF:
            self._emit_byte(Op.DUP_OFFSET)
            self._emit_byte(offset & 0xFF)
        else:
            self._emit_byte(Op.DUP_OFFSET_16)
            self._emit_i16(offset)

    def drop_to_stack(self, offset: int) -> None:
        if offset <= 0xFF:
            self._emit_byte(Op.DROP_TO_STACK)
            self._emit_byte(offset & 0xFF)
        else:
            self._emit_byte(Op.DROP_TO_STACK_16)
            self._emit_i16(offset)

    def add_int32(self) -> None:
        self._emit_byte(Op.ADD_INT32)

    def sub_int32(self) -> None:
        self._emit_byte(Op.SUB_INT32)

    def mul_int32(self) -> None:
        self._emit_byte(Op.MUL_INT32)

    def div_int32(self) -> None:
        self._emit_byte(Op.DIV_INT32)

    def mod_int32(self) -> None:
        self._emit_byte(Op.MOD_INT32)

    def dup_from_global(self, index: int) -> None:
        self._emit_byte(Op.DUP_FROM_GLOBAL)
        self._emit_i16(index)

    def drop_to_global(self, index: int) -> None:
        self._emit_byte(Op.DROP_TO_GLOBAL)
        self._emit_i16(index)

    def bit_shift_left(self) -> None:
        self._emit_byte(Op.BIT_SHIFT_LEFT)

    def bit_shift_right(self) -> None:
        self._emit_byte(Op.BIT_SHIFT_RIGHT)

    def test_lt_int32(self) -> None:
        self._emit_byte(Op.TEST_LT_INT32)

    def test_ge_int32(self) -> None:
        self._emit_byte(Op.TEST_GE_INT32)

    def get_heap_bits(self) -> None:
        """Read bits from heap. Stack: push numBits, push startBit, getHeapBits."""
        self._emit_byte(Op.GET_HEAP_BITS)

    def get_heap_byte(self) -> None:
        self._emit_byte(Op.GET_HEAP_BYTE)

    # ── Build ────────────────────────────────────────────────────────────

    def build(self) -> bytes:
        """Assemble the final program binary with header, function table, and bytecode."""
        self._resolve_labels()

        func_table_size = len(self._functions) * _FUNC_ENTRY_SIZE
        code_base = _HEADER_SIZE + func_table_size

        # Build function table
        func_table = bytearray()
        for f in self._functions:
            func_table.extend(struct.pack("<hH", f.function_id, code_base + f.code_offset))

        # Assemble program
        program_size = _HEADER_SIZE + func_table_size + len(self._code)
        program = bytearray(program_size)

        # Header (checksum filled last)
        struct.pack_into("<HHH", program, 2, program_size, len(self._functions), self._num_globals)
        struct.pack_into("<H", program, 8, self._heap_size)

        # Function table + code
        program[_HEADER_SIZE : _HEADER_SIZE + func_table_size] = func_table
        program[code_base:] = self._code

        # Checksum
        checksum = compute_program_checksum(program)
        struct.pack_into("<H", program, 0, checksum)

        return bytes(program)

    # ── Internal ─────────────────────────────────────────────────────────

    def _emit_byte(self, value: int) -> None:
        self._code.append(value & 0xFF)

    def _emit_i16(self, value: int) -> None:
        self._code.extend(struct.pack("<h", value & 0xFFFF if value >= 0 else value))

    def _emit_i32(self, value: int) -> None:
        self._code.extend(struct.pack("<i", value))

    def _resolve_labels(self) -> None:
        """Patch all label references with actual code offsets."""
        for fixup in self._fixups:
            if fixup.label not in self._labels:
                raise ValueError(f"Undefined label: {fixup.label!r}")
            target = self._labels[fixup.label]
            struct.pack_into("<h", self._code, fixup.code_offset, target)
