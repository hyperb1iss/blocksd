"""Tests for config-related packet builder methods."""

from __future__ import annotations

from blocksd.protocol.builder import (
    HostPacketBuilder,
    build_config_request,
    build_config_request_user_sync,
    build_config_set,
)
from blocksd.protocol.constants import ROLI_SYSEX_HEADER


def _valid_sysex(data: bytes) -> bool:
    """Check basic SysEx framing."""
    return data[:5] == ROLI_SYSEX_HEADER and data[-1] == 0xF7 and len(data) >= 8


class TestBuildConfigSet:
    def test_valid_sysex(self):
        packet = build_config_set(0, 10, 50)
        assert _valid_sysex(packet)

    def test_different_values(self):
        p1 = build_config_set(0, 10, 50)
        p2 = build_config_set(0, 10, 100)
        assert p1 != p2

    def test_device_index_in_header(self):
        packet = build_config_set(3, 10, 50)
        assert packet[5] == 3


class TestBuildConfigRequest:
    def test_valid_sysex(self):
        packet = build_config_request(0, 10)
        assert _valid_sysex(packet)

    def test_different_items(self):
        p1 = build_config_request(0, 10)
        p2 = build_config_request(0, 20)
        assert p1 != p2


class TestBuildConfigRequestUserSync:
    def test_valid_sysex(self):
        packet = build_config_request_user_sync(0)
        assert _valid_sysex(packet)


class TestHostPacketBuilderConfig:
    def test_config_set_builds(self):
        b = HostPacketBuilder()
        b.write_sysex_header(0)
        b.config_set(10, 42)
        packet = b.build()
        assert _valid_sysex(packet)

    def test_config_request_builds(self):
        b = HostPacketBuilder()
        b.write_sysex_header(0)
        b.config_request(10)
        packet = b.build()
        assert _valid_sysex(packet)

    def test_config_request_user_sync_builds(self):
        b = HostPacketBuilder()
        b.write_sysex_header(0)
        b.config_request_user_sync()
        packet = b.build()
        assert _valid_sysex(packet)
