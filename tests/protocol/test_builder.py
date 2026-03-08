"""Tests for host packet builder."""

from blocksd.protocol.builder import (
    build_begin_api_mode,
    build_end_api_mode,
    build_ping,
    build_request_topology,
)
from blocksd.protocol.constants import ROLI_SYSEX_HEADER


class TestHostPacketBuilder:
    def test_ping_has_sysex_framing(self) -> None:
        packet = build_ping(0)
        assert packet[:5] == ROLI_SYSEX_HEADER
        assert packet[-1] == 0xF7

    def test_ping_device_index(self) -> None:
        packet = build_ping(3)
        assert packet[5] == 3  # device index byte

    def test_begin_api_mode_structure(self) -> None:
        packet = build_begin_api_mode(0)
        assert packet[:5] == ROLI_SYSEX_HEADER
        assert packet[-1] == 0xF7
        assert len(packet) > 7  # header + index + payload + checksum + F7

    def test_end_api_mode_structure(self) -> None:
        packet = build_end_api_mode(0)
        assert packet[:5] == ROLI_SYSEX_HEADER
        assert packet[-1] == 0xF7

    def test_request_topology_structure(self) -> None:
        packet = build_request_topology(0)
        assert packet[:5] == ROLI_SYSEX_HEADER
        assert packet[-1] == 0xF7

    def test_different_commands_produce_different_packets(self) -> None:
        ping = build_ping(0)
        begin = build_begin_api_mode(0)
        end = build_end_api_mode(0)
        assert ping != begin
        assert begin != end
