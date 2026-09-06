"""MIDI device scanning — finds ROLI Blocks by matching port names.

Ported from roli_MIDIDeviceDetector.cpp.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from blocksd.device.coremidi import CoreMidiEndpoint

log = logging.getLogger(__name__)

# ROLI MIDI port names contain "BLOCK" or "Block"
_BLOCK_PATTERN = re.compile(r"\bBLOCK\b|\bBlock\b")

# Suffixes added by ALSA/JACK that differ between input and output
_STRIP_SUFFIXES = re.compile(r"\s*(IN|OUT)\)$|\s*\[\d+\]$")


@dataclass(frozen=True)
class MidiPortPair:
    """Matched MIDI input + output port for a single ROLI device."""

    input_port: int
    output_port: int
    name: str
    endpoint_ids: tuple[int, int] | None = None
    occurrence: int = 0

    @property
    def key(self) -> str:
        """Identity independent of the current enumeration indices."""
        if self.endpoint_ids is not None:
            return f"coremidi:{self.endpoint_ids[0]}:{self.endpoint_ids[1]}"
        return f"named:{self.name}:{self.occurrence}"


def _is_blocks_port(name: str) -> bool:
    """Check if a MIDI port name belongs to a ROLI Blocks device."""
    return _BLOCK_PATTERN.search(name) is not None


def _clean_port_name(name: str) -> str:
    """Normalize port name for input/output matching.

    Strips trailing suffixes like ' IN)', ' OUT)', '[0]' that differ
    between the input and output side of the same device.
    """
    return _STRIP_SUFFIXES.sub("", name.strip())


def scan_for_blocks() -> list[MidiPortPair]:
    """Scan MIDI ports and return matched input/output pairs for ROLI Blocks.

    Find inputs containing "BLOCK" or "Block". CoreMIDI hardware pairs by
    owning entity and retains endpoint UIDs across index changes. Other
    backends and virtual endpoints pair by normalized name and occurrence.
    """
    import rtmidi

    midi_in = rtmidi.MidiIn()
    midi_out = rtmidi.MidiOut()

    try:
        endpoints = None
        if midi_in.get_current_api() == rtmidi.API_MACOSX_CORE:
            from blocksd.device.coremidi import endpoint_snapshot

            endpoints = endpoint_snapshot()
        input_ports = midi_in.get_ports()
        output_ports = midi_out.get_ports()
        if endpoints is not None and endpoints != endpoint_snapshot():
            raise RuntimeError("CoreMIDI endpoints changed during discovery")
        return _pair_ports(input_ports, output_ports, endpoints)
    finally:
        midi_in.delete()
        midi_out.delete()


def _pair_ports(
    input_ports: list[str],
    output_ports: list[str],
    endpoints: tuple[list[CoreMidiEndpoint], list[CoreMidiEndpoint]] | None = None,
) -> list[MidiPortPair]:
    if endpoints is not None and (
        len(endpoints[0]) != len(input_ports) or len(endpoints[1]) != len(output_ports)
    ):
        raise RuntimeError("CoreMIDI endpoint count changed during discovery")
    pairs: list[MidiPortPair] = []
    used_outputs: set[int] = set()

    for in_idx, in_name in enumerate(input_ports):
        if not _is_blocks_port(in_name):
            continue

        cleaned_in = _clean_port_name(in_name)

        # Count how many times we've already matched this cleaned name
        input_occurrences = sum(1 for p in pairs if _clean_port_name(p.name) == cleaned_in)

        # Native entities distinguish identically named physical devices.
        matched_out_idx = -1
        for out_idx, out_name in enumerate(output_ports):
            if out_idx in used_outputs:
                continue
            if endpoints is not None and endpoints[0][in_idx].entity:
                matches = endpoints[0][in_idx].entity == endpoints[1][out_idx].entity
            else:
                matches = _clean_port_name(out_name) == cleaned_in and (
                    endpoints is None or endpoints[1][out_idx].entity == 0
                )
            if matches:
                matched_out_idx = out_idx
                break

        if matched_out_idx >= 0:
            ids = (
                (endpoints[0][in_idx].uid, endpoints[1][matched_out_idx].uid)
                if endpoints is not None
                else None
            )
            pairs.append(MidiPortPair(in_idx, matched_out_idx, in_name, ids, input_occurrences))
            used_outputs.add(matched_out_idx)
            log.debug("Found ROLI device: %s (in=%d, out=%d)", in_name, in_idx, matched_out_idx)
        else:
            log.warning("No matching output for ROLI input: %s", in_name)

    return pairs
