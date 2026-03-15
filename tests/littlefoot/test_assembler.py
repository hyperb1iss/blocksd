"""Tests for LittleFoot bytecode assembler."""

from __future__ import annotations

import struct

import pytest

from blocksd.littlefoot.assembler import (
    BytecodeAssembler,
    compute_function_id,
    compute_program_checksum,
)
from blocksd.littlefoot.opcodes import Op

# ── FunctionID Computation ───────────────────────────────────────────────────


class TestComputeFunctionId:
    def test_repaint(self):
        """repaint/v — the standard repaint callback."""
        fid = compute_function_id("repaint/v")
        # Should be a valid int16
        assert -32768 <= fid <= 32767

    def test_deterministic(self):
        assert compute_function_id("foo/vi") == compute_function_id("foo/vi")

    def test_different_signatures_differ(self):
        assert compute_function_id("foo/vi") != compute_function_id("bar/vi")

    def test_return_type_excluded(self):
        """Signatures differing only in return type should still differ
        because the return type character position is excluded but
        length and other chars may change behavior."""
        id1 = compute_function_id("foo/vi")
        id2 = compute_function_id("foo/ii")
        # These should differ because 'v' vs 'i' as return type changes
        # the chars being hashed (params are different lengths)
        # Actually with same params and different return type:
        # "foo/vi" skips 'v', hashes: f,o,o,/,i → same as
        # "foo/ii" skips first 'i', hashes: f,o,o,/,i → SAME hash but different length
        # foo/vi len=6, foo/ii len=6 → same length too
        # So the IDs should be THE SAME — the return type is intentionally excluded
        assert id1 == id2

    def test_known_signature_make_argb(self):
        """makeARGB/iiiii should produce a consistent ID."""
        fid = compute_function_id("makeARGB/iiiii")
        assert isinstance(fid, int)
        assert -32768 <= fid <= 32767

    def test_known_signature_fill_pixel(self):
        fid = compute_function_id("fillPixel/viii")
        assert isinstance(fid, int)
        assert -32768 <= fid <= 32767


# ── Program Checksum ─────────────────────────────────────────────────────────


class TestProgramChecksum:
    def test_matches_header_format(self):
        """Checksum should be uint16."""
        program = bytearray(20)
        struct.pack_into("<H", program, 2, 20)  # program_size = 20
        cs = compute_program_checksum(program)
        assert 0 <= cs <= 0xFFFF

    def test_different_data_different_checksum(self):
        p1 = bytearray([0] * 20)
        p2 = bytearray([0] * 20)
        p2[5] = 0xFF
        struct.pack_into("<H", p1, 2, 20)
        struct.pack_into("<H", p2, 2, 20)
        assert compute_program_checksum(p1) != compute_program_checksum(p2)


# ── BytecodeAssembler ────────────────────────────────────────────────────────


class TestAssemblerBasic:
    def test_empty_program(self):
        asm = BytecodeAssembler()
        program = asm.build()
        # Header only: 10 bytes
        assert len(program) == 10
        # Check header fields
        size = struct.unpack_from("<H", program, 2)[0]
        assert size == 10

    def test_single_halt(self):
        asm = BytecodeAssembler()
        asm.begin_function("test/v")
        asm.halt()
        program = asm.build()
        # Header(10) + function table(4) + halt(1) = 15
        assert len(program) == 15

    def test_function_count(self):
        asm = BytecodeAssembler()
        asm.begin_function("foo/v")
        asm.halt()
        asm.begin_function("bar/v")
        asm.halt()
        program = asm.build()
        num_funcs = struct.unpack_from("<H", program, 4)[0]
        assert num_funcs == 2

    def test_heap_size_in_header(self):
        asm = BytecodeAssembler(heap_size=450)
        program = asm.build()
        heap_size = struct.unpack_from("<H", program, 8)[0]
        assert heap_size == 450

    def test_num_globals_in_header(self):
        asm = BytecodeAssembler(num_globals=3)
        program = asm.build()
        num_globals = struct.unpack_from("<H", program, 6)[0]
        assert num_globals == 3


class TestAssemblerOpcodes:
    def _get_code(self, asm: BytecodeAssembler) -> bytes:
        """Extract just the bytecode portion (after header + func table)."""
        program = asm.build()
        num_funcs = struct.unpack_from("<H", program, 4)[0]
        code_start = 10 + num_funcs * 4
        return program[code_start:]

    def test_push0(self):
        asm = BytecodeAssembler()
        asm.begin_function("test/v")
        asm.push0()
        code = self._get_code(asm)
        assert code[0] == Op.PUSH_0

    def test_push8(self):
        asm = BytecodeAssembler()
        asm.begin_function("test/v")
        asm.push8(42)
        code = self._get_code(asm)
        assert code[0] == Op.PUSH_8
        assert code[1] == 42

    def test_push16(self):
        asm = BytecodeAssembler()
        asm.begin_function("test/v")
        asm.push16(1000)
        code = self._get_code(asm)
        assert code[0] == Op.PUSH_16
        val = struct.unpack_from("<h", code, 1)[0]
        assert val == 1000

    def test_push_int_auto(self):
        asm = BytecodeAssembler()
        asm.begin_function("test/v")
        asm.push_int(0)
        asm.push_int(1)
        asm.push_int(42)
        asm.push_int(1000)
        code = self._get_code(asm)
        assert code[0] == Op.PUSH_0
        assert code[1] == Op.PUSH_1
        assert code[2] == Op.PUSH_8
        assert code[4] == Op.PUSH_16

    def test_dup_offset_optimized(self):
        asm = BytecodeAssembler()
        asm.begin_function("test/v")
        asm.dup_offset(1)
        asm.dup_offset(7)
        asm.dup_offset(8)
        code = self._get_code(asm)
        # All offsets use the general form (firmware compat — no fast-path)
        assert code[0] == Op.DUP_OFFSET
        assert code[1] == 1
        assert code[2] == Op.DUP_OFFSET
        assert code[3] == 7
        assert code[4] == Op.DUP_OFFSET
        assert code[5] == 8

    def test_call_native(self):
        asm = BytecodeAssembler()
        asm.begin_function("test/v")
        asm.call_native(0x1234)
        code = self._get_code(asm)
        assert code[0] == Op.CALL_NATIVE
        val = struct.unpack_from("<h", code, 1)[0]
        assert val == 0x1234


class TestAssemblerLabels:
    def test_forward_jump(self):
        asm = BytecodeAssembler()
        asm.begin_function("test/v")
        asm.jump("end")
        asm.push0()
        asm.label("end")
        asm.halt()
        program = asm.build()
        # Should build without error
        assert len(program) > 10

    def test_backward_jump(self):
        asm = BytecodeAssembler()
        asm.begin_function("test/v")
        asm.label("top")
        asm.push0()
        asm.jump("top")
        program = asm.build()
        assert len(program) > 10

    def test_undefined_label_raises(self):
        asm = BytecodeAssembler()
        asm.begin_function("test/v")
        asm.jump("nonexistent")
        with pytest.raises(ValueError, match="Undefined label"):
            asm.build()

    def test_checksum_valid(self):
        """Built program should have a valid checksum in its header."""
        asm = BytecodeAssembler(heap_size=100)
        asm.begin_function("test/v")
        asm.push8(42)
        asm.ret_void(0)
        program = bytearray(asm.build())

        stored_checksum = struct.unpack_from("<H", program, 0)[0]
        # Recalculate
        program[0] = 0
        program[1] = 0
        computed = compute_program_checksum(program)
        assert stored_checksum == computed
