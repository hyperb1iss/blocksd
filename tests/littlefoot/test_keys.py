"""LUMI renderer vectors checked against the upstream LittleFoot VM."""

from __future__ import annotations

import struct

from blocksd.littlefoot.assembler import compute_function_id, compute_program_checksum
from blocksd.littlefoot.keys import KEY_COUNT, KEY_HEAP_SIZE, key_led_program, key_led_program_size

# Upstream Runner executes initialise with (touch=true, lighting=false), then
# disables the status overlay. Message callbacks echo matching challenge nonces;
# repaint draws each RGB565 key once.
_VERIFIED_PROGRAM = bytes.fromhex(
    "8ca28200030000003000648c16008d6f"
    "21000bea61000b078e7e0b0c07a38105"
    "000b100d182436035e00100d10220b18"
    "020d0518030d0b20400d032d0d061804"
    "0d0520400d022d0d051805400d032d0e"
    "ff0007833f070bc2080c200122000805"
    "0018010f44454c422402800018020d02"
    "2402800018030d020f44454c4207d2ce"
    "0503"
)


def test_matches_program_executed_by_upstream_vm():
    assert key_led_program() == _VERIFIED_PROGRAM


def test_has_initialise_repaint_and_message_callbacks():
    program = key_led_program()
    assert struct.unpack_from("<H", program, 4)[0] == 3
    assert struct.unpack_from("<h", program, 10)[0] == compute_function_id("initialise/v")
    assert struct.unpack_from("<h", program, 14)[0] == compute_function_id("repaint/v")
    assert struct.unpack_from("<h", program, 18)[0] == compute_function_id("handleMessage/viii")


def test_pixel_heap_follows_program_and_fits_all_keys():
    program = key_led_program()
    assert KEY_COUNT == 24
    assert KEY_HEAP_SIZE == 48
    assert struct.unpack_from("<H", program, 8)[0] == KEY_HEAP_SIZE
    assert struct.unpack_from("<H", program, 2)[0] == key_led_program_size() == len(program)


def test_program_checksum_is_valid():
    program = key_led_program()
    assert struct.unpack_from("<H", program)[0] == compute_program_checksum(bytearray(program))
