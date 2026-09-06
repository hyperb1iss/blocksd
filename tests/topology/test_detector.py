"""Tests for MIDI port name matching — no hardware required."""

from unittest.mock import Mock

import pytest

from blocksd.topology.detector import (
    _clean_port_name,
    _is_blocks_port,
    _pair_ports,
    scan_for_blocks,
)


class TestBlocksPortDetection:
    def test_lightpad_block(self) -> None:
        assert _is_blocks_port("Lightpad BLOCK")

    def test_seaboard_block(self) -> None:
        assert _is_blocks_port("Seaboard Block")

    def test_lumi_keys_block(self) -> None:
        assert _is_blocks_port("LUMI Keys Block")

    def test_non_block_device(self) -> None:
        assert not _is_blocks_port("USB MIDI Interface")

    def test_non_block_with_block_substring(self) -> None:
        # "blocked" contains "block" but not as a word boundary
        assert not _is_blocks_port("blocked port")

    def test_empty_name(self) -> None:
        assert not _is_blocks_port("")


class TestPortNameCleaning:
    def test_strips_in_suffix(self) -> None:
        assert _clean_port_name("Lightpad BLOCK IN)") == "Lightpad BLOCK"

    def test_strips_out_suffix(self) -> None:
        assert _clean_port_name("Lightpad BLOCK OUT)") == "Lightpad BLOCK"

    def test_strips_index_suffix(self) -> None:
        assert _clean_port_name("Lightpad BLOCK [0]") == "Lightpad BLOCK"

    def test_preserves_clean_name(self) -> None:
        assert _clean_port_name("Lightpad BLOCK") == "Lightpad BLOCK"

    def test_strips_whitespace(self) -> None:
        assert _clean_port_name("  Lightpad BLOCK  ") == "Lightpad BLOCK"

    def test_input_output_match(self) -> None:
        """Input and output names should clean to the same base name."""
        cleaned_in = _clean_port_name("Lightpad BLOCK IN)")
        cleaned_out = _clean_port_name("Lightpad BLOCK OUT)")
        assert cleaned_in == cleaned_out


def test_native_entities_pair_duplicates_in_different_enumeration_orders():
    from blocksd.device.coremidi import CoreMidiEndpoint

    pairs = _pair_ports(
        ["Lightpad BLOCK", "Lightpad BLOCK"],
        ["Lightpad BLOCK", "Lightpad BLOCK"],
        (
            [CoreMidiEndpoint(10, 100), CoreMidiEndpoint(11, 101)],
            [CoreMidiEndpoint(21, 101), CoreMidiEndpoint(20, 100)],
        ),
    )
    assert [(pair.input_port, pair.output_port) for pair in pairs] == [(0, 1), (1, 0)]
    assert [pair.endpoint_ids for pair in pairs] == [(10, 20), (11, 21)]
    assert pairs[0].key != pairs[1].key


def test_named_pairs_preserve_identity_when_unrelated_port_is_removed():
    first = _pair_ports(["Keyboard", "Lightpad BLOCK"], ["Keyboard", "Lightpad BLOCK"])
    second = _pair_ports(["Lightpad BLOCK"], ["Lightpad BLOCK"])
    assert first[0].key == second[0].key
    assert first[0].input_port != second[0].input_port


def test_virtual_name_cannot_consume_a_physical_destination():
    from blocksd.device.coremidi import CoreMidiEndpoint

    pairs = _pair_ports(
        ["Lightpad BLOCK", "Lightpad BLOCK"],
        ["Lightpad BLOCK", "Lightpad BLOCK"],
        (
            [CoreMidiEndpoint(1, 0), CoreMidiEndpoint(2, 10)],
            [CoreMidiEndpoint(3, 10), CoreMidiEndpoint(4, 0)],
        ),
    )
    assert [pair.endpoint_ids for pair in pairs] == [(1, 4), (2, 3)]


def test_native_count_mismatch_is_rejected():
    with pytest.raises(RuntimeError, match="count changed"):
        _pair_ports(["Lightpad BLOCK"], [], ([], []))


def test_scan_rejects_hotplug_during_enumeration_and_releases_clients(monkeypatch):
    import rtmidi

    from blocksd.device import coremidi

    midi_in = Mock()
    midi_out = Mock()
    core_api = object()
    monkeypatch.setattr(rtmidi, "API_MACOSX_CORE", core_api)
    midi_in.get_current_api.return_value = core_api
    midi_in.get_ports.return_value = ["Lightpad BLOCK"]
    midi_out.get_ports.return_value = ["Lightpad BLOCK"]
    monkeypatch.setattr(rtmidi, "MidiIn", lambda: midi_in)
    monkeypatch.setattr(rtmidi, "MidiOut", lambda: midi_out)
    monkeypatch.setattr(
        coremidi,
        "endpoint_snapshot",
        Mock(side_effect=[([coremidi.CoreMidiEndpoint(1, 1)], []), ([], [])]),
    )
    with pytest.raises(RuntimeError, match="changed during discovery"):
        scan_for_blocks()
    midi_in.delete.assert_called_once()
    midi_out.delete.assert_called_once()
