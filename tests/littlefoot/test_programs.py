"""Tests for pre-assembled LittleFoot programs."""

from __future__ import annotations

import struct

from blocksd.littlefoot.assembler import compute_function_id, compute_program_checksum
from blocksd.littlefoot.programs import bitmap_led_program, bitmap_led_program_size


class TestBitmapLEDProgram:
    def test_assembles_without_error(self):
        program = bitmap_led_program()
        assert isinstance(program, bytes)
        assert len(program) > 10

    def test_size_matches(self):
        assert bitmap_led_program_size() == len(bitmap_led_program())

    def test_valid_header(self):
        program = bitmap_led_program()
        size = struct.unpack_from("<H", program, 2)[0]
        assert size == len(program)

    def test_one_function(self):
        program = bitmap_led_program()
        num_funcs = struct.unpack_from("<H", program, 4)[0]
        assert num_funcs == 1

    def test_heap_size_450(self):
        """15x15 grid x 2 bytes per pixel = 450."""
        program = bitmap_led_program()
        heap_size = struct.unpack_from("<H", program, 8)[0]
        assert heap_size == 450

    def test_function_is_repaint(self):
        """The single function should have the repaint FunctionID."""
        program = bitmap_led_program()
        func_id = struct.unpack_from("<h", program, 10)[0]
        expected = compute_function_id("repaint/v")
        assert func_id == expected

    def test_checksum_valid(self):
        program = bytearray(bitmap_led_program())
        stored = struct.unpack_from("<H", program, 0)[0]
        program[0] = 0
        program[1] = 0
        computed = compute_program_checksum(program)
        assert stored == computed

    def test_cached(self):
        """Repeated calls return the same object (lru_cache)."""
        assert bitmap_led_program() is bitmap_led_program()

    def test_reasonable_size(self):
        """Should be compact — under 200 bytes for such a simple program."""
        assert bitmap_led_program_size() < 200
