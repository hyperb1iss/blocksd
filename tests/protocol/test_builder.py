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


class TestProgramEvents:
    def test_challenge_matches_upstream_cpp_packing(self) -> None:
        from blocksd.protocol.builder import build_program_event

        # Golden vector produced by the upstream Packed7BitArrayBuilder.
        expected = bytes.fromhex("f0002110771603440a311224000000007e7f7f7f0f45f7")
        assert build_program_event(22, (0x424C4544, 2, 0x7FFFFFFF)) == expected

    def test_signed_arguments_match_upstream_cpp_packing(self) -> None:
        from blocksd.protocol.builder import build_program_event

        expected = bytes.fromhex("f00021107716037f7f7f7f0f00000000000000001025f7")
        assert build_program_event(22, (-1, 0, -2147483648)) == expected
