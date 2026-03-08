"""Packet checksum — ported from roli_BitPackingUtilities.h."""


def calculate_checksum(data: bytes | bytearray) -> int:
    """Calculate ROLI packet checksum over payload bytes.

    Algorithm: accumulate (checksum * 2 + byte) starting from size, mask to 7 bits.
    """
    checksum = len(data) & 0xFF
    for byte in data:
        checksum = (checksum + (checksum * 2 + byte)) & 0xFF
    return checksum & 0x7F
