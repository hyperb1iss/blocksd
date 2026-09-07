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

    def test_initialise_repaint_and_message_callbacks(self):
        program = bitmap_led_program()
        num_funcs = struct.unpack_from("<H", program, 4)[0]
        assert num_funcs == 3
        assert struct.unpack_from("<h", program, 10)[0] == compute_function_id("initialise/v")
        assert struct.unpack_from("<h", program, 18)[0] == compute_function_id("handleMessage/viii")

    def test_heap_size_450(self):
        """15x15 grid x 2 bytes per pixel = 450."""
        program = bitmap_led_program()
        heap_size = struct.unpack_from("<H", program, 8)[0]
        assert heap_size == 450

    def test_function_is_repaint(self):
        """The second function exposes the repaint callback."""
        program = bitmap_led_program()
        func_id = struct.unpack_from("<h", program, 14)[0]
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


# Executed by the unchanged upstream VM: matching challenge nonces echoed,
# every RGB565 pixel painted once per repaint, and status overlay disabled.
_VERIFIED_PROGRAM = bytes.fromhex(
    "1de8910003000000c201648c16008d6f"
    "1c000bea72000b078e7e05000b100d0f"
    "2436036f000b100d0f24360369001018"
    "020d0f22200d1022180218020d051803"
    "0d0b20400d032d0d0618040d0520400d"
    "022d0d051805400d032d0eff0007833f"
    "070bc2080c20012600080c20011d0008"
    "050018010f44454c4224028f0018020c"
    "24028f0018030c0f44454c4207d2ce05"
    "03"
)


def test_matches_program_executed_by_upstream_vm():
    assert bitmap_led_program() == _VERIFIED_PROGRAM
