"""LUMI renderer vectors checked against the upstream LittleFoot VM."""

from __future__ import annotations

import struct

from blocksd.littlefoot.assembler import compute_function_id, compute_program_checksum
from blocksd.littlefoot.keys import KEY_COUNT, KEY_HEAP_SIZE, key_led_program, key_led_program_size

# Upstream Runner verifies setLocalConfig(36, 100) during initialise and each
# matching readiness challenge, including unchanged-code reuploads. Invalid
# challenges and repaint never write config; touch=true/lighting=false and
# every RGB565 pixel remain unchanged across black, white, and varied frames.
_VERIFIED_PROGRAM = bytes.fromhex(
    "1a079000030000003000648c16008d6f28000bea68000d640d2407f6f80b078e7e0b0c07a38105000b100d1824"
    "36036500100d10220b18020d0518030d0b20400d032d0d0618040d0520400d022d0d051805400d032d0eff0007"
    "833f070bc2080c2001290008050018010f44454c4224028e0018020d0224028e000d640d2407f6f818030d020f"
    "44454c4207d2ce0503"
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
