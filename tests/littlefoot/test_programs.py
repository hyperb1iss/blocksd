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

    def test_heap_size_two_banks(self):
        """Two 15x15 RGB565 banks consume 900 bytes."""
        program = bitmap_led_program()
        heap_size = struct.unpack_from("<H", program, 8)[0]
        assert heap_size == 900

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
        """Program and both pixel banks fit the 7200-byte device memory."""
        assert bitmap_led_program_size() + 900 <= 7200


# Executed by the upstream VM: partial inactive-bank writes stay invisible,
# identities remain idempotent, and presentation ACKs follow all 225 draws.
_VERIFIED_PROGRAM = bytes.fromhex(
    "3186da01030006008403648c16008d6f1c000bead1000b078e7e05001c00001c05000b1d05001c03000338001c"
    "02001d01001c03001d04001c01001c03000b1d030018010e100e220b100d0f2436039e000b100d0f2436039800"
    "1018020d0f22200d1022180320180218020d0518030d0b20400d032d0d0618040d0520400d022d0d051805400d"
    "032d0eff0007833f070bc2080c20015200080c20014900080818031c00002402cb00180203b90018030c0f4445"
    "4c4207d2ce1003cb0010180418030f00414c422007d2ce08080808050018010f44454c4224020f0118020c2402"
    "d80118030c243503d80118031c00002403090118031d00000b1d01000b1d02000b1d03000b1d04000c1d050005"
    "0318010f00504c422403280118010f01504c4224037a0101d80118021c00002402cc0118030c243503d8011803"
    "1c04002403580118031c0400240c2402d8011c01000b2403d8010160011c01000b2402d8011c0300036f011c03"
    "0018042402d8010b1d020018031d0300050318021c00002402cc0118030c243503d80118031c04002403aa0118"
    "031c0400240c2402d8011c01000c2403d80101b2011c01000c2402d8011c030003c1011c030018042402d8010c"
    "1d020018031d03000503180318030f524e4c4207d2ce0503"
)


def test_matches_program_executed_by_upstream_vm():
    assert bitmap_led_program() == _VERIFIED_PROGRAM
