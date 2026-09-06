"""Avoid opening a different device when CoreMIDI indices change."""

import asyncio
from unittest.mock import Mock

import pytest

from blocksd.device.connection import open_connection


@pytest.mark.parametrize("phase", ["before", "after", "output_failure"])
async def test_failed_open_releases_both_native_clients(monkeypatch, phase):
    import rtmidi

    from blocksd.device import coremidi

    midi_in = Mock()
    midi_out = Mock()
    monkeypatch.setattr(rtmidi, "MidiIn", lambda: midi_in)
    monkeypatch.setattr(rtmidi, "MidiOut", lambda: midi_out)
    snapshots = [(3, 4)] if phase == "before" else [(1, 2), (3, 4)]
    monkeypatch.setattr(coremidi, "endpoint_ids", Mock(side_effect=snapshots))
    if phase == "output_failure":
        midi_out.open_port.side_effect = RuntimeError("port disappeared")
    with pytest.raises(RuntimeError):
        open_connection(0, 0, asyncio.get_running_loop(), endpoint_ids=(1, 2))
    midi_in.close_port.assert_called_once()
    midi_in.delete.assert_called_once()
    midi_out.close_port.assert_called_once()
    midi_out.delete.assert_called_once()
    if phase == "before":
        midi_in.open_port.assert_not_called()
    midi_out.send_message.assert_not_called()
