"""Tests for serial number request/response parsing."""

from blocksd.protocol.serial import identify_device_type, parse_serial_response


class TestSerialParsing:
    def test_valid_serial_response(self) -> None:
        # Simulate a response with MAC and serial
        mac = b"48:B6:20:AA:BB:CC"
        serial = b"LPB-123456789012"
        response = b"\xf0\x00\x21\x10\x78" + mac + serial + b"\xf7"
        result = parse_serial_response(response)
        assert result == "LPB-123456789012"

    def test_no_mac_prefix(self) -> None:
        response = b"\xf0\x00\x21\x10\x78\x00\x00\xf7"
        assert parse_serial_response(response) is None

    def test_truncated_serial(self) -> None:
        mac = b"48:B6:20:AA:BB:CC"
        response = b"\xf0\x00\x21\x10\x78" + mac + b"LPB" + b"\xf7"
        assert parse_serial_response(response) is None


class TestDeviceIdentification:
    def test_lightpad_block(self) -> None:
        assert identify_device_type("LPB-123456789012") == "Lightpad Block"

    def test_seaboard_block(self) -> None:
        assert identify_device_type("SBB-123456789012") == "Seaboard Block"

    def test_lumi_keys(self) -> None:
        assert identify_device_type("LKB-123456789012") == "LUMI Keys Block"

    def test_unknown(self) -> None:
        result = identify_device_type("XYZ-123456789012")
        assert "Unknown" in result
