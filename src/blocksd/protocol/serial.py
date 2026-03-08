"""Serial number request/response parsing — ported from roli_BlockSerialReader.cpp."""

from __future__ import annotations

from blocksd.protocol.constants import MAC_PREFIX, SERIAL_DUMP_RESPONSE_HEADER


def is_serial_response(sysex_data: bytes) -> bool:
    """Check if a SysEx message is a serial dump response."""
    return sysex_data[: len(SERIAL_DUMP_RESPONSE_HEADER)] == SERIAL_DUMP_RESPONSE_HEADER


def parse_serial_response(sysex_data: bytes) -> str | None:
    """Extract 16-char serial number from a dump response.

    Response contains MAC address with prefix '48:B6:20:' followed by
    the remaining 3 octets (8 chars), then the 16-char serial number.
    """
    idx = sysex_data.find(MAC_PREFIX)
    if idx < 0:
        return None

    # MAC is 17 chars total: "48:B6:20:XX:XX:XX"
    serial_start = idx + 17
    serial_end = serial_start + 16

    if serial_end > len(sysex_data):
        return None

    serial = sysex_data[serial_start:serial_end]
    try:
        return serial.decode("ascii")
    except UnicodeDecodeError:
        return None


def identify_device_type(serial: str) -> str:
    """Identify device type from serial number prefix."""
    prefixes = {
        "LPB": "Lightpad Block",
        "LPM": "Lightpad Block M",
        "SBB": "Seaboard Block",
        "LKB": "LUMI Keys Block",
        "LIC": "Live Block",
        "LOC": "Loop Block",
        "DCB": "Developer Control Block",
        "TCB": "Touch Block",
    }
    prefix = serial[:3] if len(serial) >= 3 else ""
    return prefixes.get(prefix, f"Unknown ({prefix})")
